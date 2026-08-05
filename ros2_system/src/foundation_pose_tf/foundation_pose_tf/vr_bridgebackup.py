#!/usr/bin/env python3
"""
vr_bridge.py
Puente entre Unity y UFactory Lite 6.
ESTRATEGIA: Modo 1 (ServoJ - Control por Posición) basado en script original funcional.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool

from xarm_msgs.srv import MoveJoint, SetInt16, SetInt16ById, Call
from xarm_msgs.msg import RobotMsg
from rclpy.qos import qos_profile_sensor_data # <-- La cura para la sordera, aplicada al tópico correcto
import time

class TeleopBridgeNode(Node):

    def __init__(self):
        super().__init__('teleop_bridge_node')

        self.declare_parameter('input_topic', '/vr_teleop_commands')
        self.declare_parameter('num_joints', 6)
        self.declare_parameter('max_step_rad', 0.015)

        input_topic = self.get_parameter('input_topic').value
        self.num_joints = self.get_parameter('num_joints').value
        self.max_step_rad = self.get_parameter('max_step_rad').value

        self.last_commanded = None      
        self.pending_target = None      

        self.initialized = False
        self.robot_ok = False
        self.in_fault = False
        self.configuring = False        # True mientras la secuencia async de configuración está en curso
        self.config_just_completed = False

        self.cli_clean_error = self.create_client(Call, '/ufactory/clean_error')
        self.cli_motion_enable = self.create_client(SetInt16ById, '/ufactory/motion_enable')
        self.cli_set_mode = self.create_client(SetInt16, '/ufactory/set_mode')
        self.cli_set_state = self.create_client(SetInt16, '/ufactory/set_state')
        self.cli_set_servo_angle_j = self.create_client(MoveJoint, '/ufactory/set_servo_angle_j')

        # Suscriptor a Unity: el ROS-TCP-Connector publica en RELIABLE por defecto,
        # así que aquí nos quedamos con el QoS default (compatible de sobra).
        self.sub = self.create_subscription(
            JointState,
            input_topic,
            self.unity_callback,
            10
        )

        # Suscriptor al estado físico real del robot.
        # El driver de xArm publica /ufactory/robot_states en BEST_EFFORT, así que
        # AQUÍ es donde va qos_profile_sensor_data — si no, la suscripción nunca
        # conecta y el nodo se queda esperando para siempre en silencio.
        self.sub_robot_states = self.create_subscription(
            RobotMsg,
            '/ufactory/robot_states',
            self.robot_states_callback,
            qos_profile_sensor_data
        )

        self.status_pub = self.create_publisher(Bool, '/teleop_bridge_status', 10)

        self.send_rate_hz = 30.0
        self.timer = self.create_timer(1.0 / self.send_rate_hz, self.send_to_robot)
        self.status_timer = self.create_timer(0.5, self.publish_status)

        self.get_logger().info('Esperando primera lectura de /ufactory/robot_states...')
        self.first_message_logged = False

    def configure_robot_for_servo(self):
        # Evita re-disparar la secuencia si ya hay una en curso
        if self.configuring:
            return
        self.configuring = True
        self.get_logger().info('Iniciando secuencia de configuración (async)...')

        # Encadenamos las 4 llamadas con add_done_callback, en vez de bloquear
        # con spin_until_future_complete. Esto es OBLIGATORIO porque esta función
        # se dispara desde dentro de robot_states_callback, que ya está siendo
        # ejecutado por el spin principal — bloquear ahí causa un deadlock.
        fut = self.cli_clean_error.call_async(Call.Request())
        fut.add_done_callback(self._on_clean_error_done)

    def _on_clean_error_done(self, fut):
        req = SetInt16ById.Request()
        req.id = 8
        req.data = 1
        fut2 = self.cli_motion_enable.call_async(req)
        fut2.add_done_callback(self._on_motion_enable_done)

    def _on_motion_enable_done(self, fut):
        req = SetInt16.Request()
        req.data = 1
        fut3 = self.cli_set_mode.call_async(req)
        fut3.add_done_callback(self._on_set_mode_done)

    def _on_set_mode_done(self, fut):
        self.get_logger().info('Modo establecido a 1 (ServoJ Position Control)')
        req = SetInt16.Request()
        req.data = 0
        fut4 = self.cli_set_state.call_async(req)
        fut4.add_done_callback(self._on_set_state_done)

    def _on_set_state_done(self, fut):
        self.get_logger().info('Estado establecido a 0 (Listo)')
        self.configuring = False
        self.config_just_completed = True

    def robot_states_callback(self, msg: RobotMsg):
        real_angles = list(msg.angle[:self.num_joints])

        if not self.initialized:
            if msg.err != 0 or msg.state == 5:
                if not self.configuring:
                    self.get_logger().warn(
                        f'Robot no listo (err={msg.err}, state={msg.state}). Configurando...'
                    )
                    self.configure_robot_for_servo()
                return  # seguimos esperando; NO bloqueamos, NO dormimos

            # err == 0 y state != 5: pero si la configuración async todavía
            # está en curso, esperamos a que termine antes de dar por listo.
            if self.configuring:
                return

            self.get_logger().info(f'Posición real leída: {real_angles}')
            self.last_commanded = real_angles
            self.initialized = True
            self.robot_ok = True
            self.get_logger().info('¡Robot listo en MODO 1! Esperando comandos de Unity...')
            return

        if msg.err != 0:
            if not self.in_fault:
                self.get_logger().error(f'¡Robot en fallo! err={msg.err}. Pausando envío.')
            self.in_fault = True
            self.robot_ok = False
            return

        if self.in_fault:
            self.get_logger().info('Error limpiado. Resincronizando con posición real...')
            self.last_commanded = real_angles
            if not self.configuring:
                self.configure_robot_for_servo()
            self.in_fault = False

        self.robot_ok = True

    def publish_status(self):
        msg = Bool()
        msg.data = bool(self.robot_ok)
        self.status_pub.publish(msg)

    def unity_callback(self, msg: JointState):
        if len(msg.position) < self.num_joints:
            return

        target_positions = [None] * self.num_joints
        for i, name in enumerate(msg.name):
            clean_name = name.replace('_', '')
            if clean_name == 'joint1': target_positions[0] = msg.position[i]
            elif clean_name == 'joint2': target_positions[1] = msg.position[i]
            elif clean_name == 'joint3': target_positions[2] = msg.position[i]
            elif clean_name == 'joint4': target_positions[3] = msg.position[i]
            elif clean_name == 'joint5': target_positions[4] = msg.position[i]
            elif clean_name == 'joint6': target_positions[5] = msg.position[i]

        # Si el mapeo por nombre falla, usamos el truco de tu script antiguo (cortar los primeros 6)
        if None in target_positions:
            target_positions = list(msg.position[:self.num_joints])

        self.pending_target = target_positions

        if not self.first_message_logged:
            self.get_logger().info('¡Primer comando de Unity recibido exitosamente!')
            self.first_message_logged = True

    def send_to_robot(self):
        if not self.initialized or not self.robot_ok or self.pending_target is None:
            return

        target = self.pending_target

        # Limitador de salto de tu script antiguo
        safe_angles = []
        for i in range(self.num_joints):
            delta = target[i] - self.last_commanded[i]
            if delta > self.max_step_rad: delta = self.max_step_rad
            elif delta < -self.max_step_rad: delta = -self.max_step_rad
            safe_angles.append(self.last_commanded[i] + delta)

        self.last_commanded = safe_angles

        req = MoveJoint.Request()
        req.angles = [float(a) for a in safe_angles]
        req.speed = 0.0     
        req.acc = 0.0
        req.mvtime = 0.0
        req.wait = False
        req.timeout = -1.0
        req.radius = -1.0
        req.relative = False

        future = self.cli_set_servo_angle_j.call_async(req)
        # Ignoramos la respuesta para no saturar la consola, a menos que sea error crítico
        future.add_done_callback(self.servo_response_callback)

    def servo_response_callback(self, future):
        try:
            res = future.result()
            if res.ret != 0:
                pass
        except Exception:
            pass

def main(args=None):
    rclpy.init(args=args)
    node = TeleopBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
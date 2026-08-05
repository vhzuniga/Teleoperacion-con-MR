# Teleoperación con MR — Guía de instalación

Guía completa para dejar corriendo este proyecto en una máquina nueva con **Ubuntu 22.04.5** y **ROS 2 Humble** ya instalados.

## 1. Herramientas base

```bash
sudo apt update
sudo apt install -y git python3-pip python3-colcon-common-extensions python3-rosdep
```

## 2. Inicializar rosdep (solo si nunca se ha hecho en esta máquina)

```bash
sudo rosdep init
rosdep update
```
Si da error de "already initialized", ignóralo — significa que ya estaba hecho.

## 3. Clonar el repositorio (con submódulos)

Este repo usa submódulos de git (`xarm_ros2`, `ROS-TCP-Endpoint`), así que **es obligatorio** el flag `--recurse-submodules`:

```bash
cd ~/Documents
git clone --recurse-submodules git@github.com:vhzuniga/Teleoperacion-con-MR.git VR---Robot---Teleoperation
```

Si alguien ya clonó sin el flag por error, se arregla así:
```bash
cd VR---Robot---Teleoperation
git submodule update --init --recursive
```

## 4. Instalar las dependencias de los paquetes ROS 2

```bash
cd ~/Documents/VR---Robot---Teleoperation/ros2_system
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
```

## 5. Compilar solo lo necesario para la teleoperación

`xarm_ros2` trae paquetes de MoveIt/Gazebo que no hacen falta para este flujo. Compilamos únicamente lo necesario:

```bash
colcon build --packages-up-to foundation_pose_tf gripper_control gripper_description xarm_api ros_tcp_endpoint
```

Si algún paquete falla por dependencia faltante, revisa el error específico antes de intentar compilar todo el workspace.

## 6. Automatizar el `source` en el `.bashrc`

Para no tener que hacer `source` cada vez que abras una terminal:

```bash
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
echo "source ~/Documents/VR---Robot---Teleoperation/ros2_system/install/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

## 7. Verificar la instalación

```bash
ros2 pkg list | grep foundation_pose_tf
```
Si aparece en la lista, la instalación quedó bien.

## 8. Lanzar el proyecto

```bash
ros2 launch foundation_pose_tf teleop_full.launch.py
```

⚠️ **Antes de lanzar, verifica que las IPs por defecto del launch file coincidan con tu red actual.** El launch usa `robot_ip` y `ros_ip` como valores fijos por defecto — si tu red es distinta (por ejemplo, en otra VM, otra oficina, u otro router), el lanzamiento fallará silenciosamente o no conectará con el robot ni con Unity.

Revisa la IP real de tu PC con:
```bash
hostname -I
```
Y compárala con el valor por defecto de `ros_ip` en `teleop_full.launch.py`. Revisa también que `robot_ip` coincida con la IP configurada en el controlador físico del Lite6.

Si no coinciden, pasa los valores correctos explícitamente:
```bash
ros2 launch foundation_pose_tf teleop_full.launch.py robot_ip:=<IP_DEL_ROBOT> ros_ip:=<IP_DE_ESTA_PC>
```

---

## Notas

- El robot debe estar encendido y en la misma red que esta PC antes de lanzar.
- Los tres procesos (ROS-TCP-Endpoint, driver del Lite6 con gripper, nodo del gripper, y `vr_bridge`) se lanzan juntos con el único comando del paso 8. `Ctrl+C` una sola vez los cierra a todos.
- Unity corre por separado (en otra máquina, típicamente Windows) y debe apuntar a la IP de `ros_ip` en el campo "ROS2 IP" dentro de la escena.

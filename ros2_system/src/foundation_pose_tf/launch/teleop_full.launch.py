"""
teleop_full.launch.py

Lanza todo lo necesario para la teleoperación VR del Lite6 en un solo comando:
  1) ros_tcp_endpoint (conexión con Unity)
  2) driver del Lite6, con gripper habilitado
  3) nodo de control del gripper (gripper_control/lite6_gripper_ws)
  4) vr_bridge (foundation_pose_tf/vr_bridge)

Colócalo en:
  ~/Documents/VR---Robot---Teleoperation/ros2_system/src/foundation_pose_tf/launch/teleop_full.launch.py

Uso:
  ros2 launch foundation_pose_tf teleop_full.launch.py

Con IPs distintas:
  ros2 launch foundation_pose_tf teleop_full.launch.py robot_ip:=192.168.1.163 ros_ip:=192.168.81.131
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_ip_arg = DeclareLaunchArgument(
        'robot_ip',
        default_value='192.168.1.163',
        description='IP del robot Lite6'
    )
    ros_ip_arg = DeclareLaunchArgument(
        'ros_ip',
        default_value='192.168.81.131',
        description='IP de esta PC, para el ROS-TCP-Endpoint (la que se coloca en Unity)'
    )

    robot_ip = LaunchConfiguration('robot_ip')
    ros_ip = LaunchConfiguration('ros_ip')

    # 1) ROS-TCP-Endpoint (conexión con Unity)
    tcp_endpoint = Node(
        package='ros_tcp_endpoint',
        executable='default_server_endpoint',
        name='ros_tcp_endpoint',
        output='screen',
        parameters=[{'ROS_IP': ros_ip}],
    )

    # 2) Driver del Lite6, con gripper habilitado
    lite6_driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare('xarm_api'),
                'launch',
                'lite6_driver.launch.py'
            ])
        ),
        launch_arguments={
            'robot_ip': robot_ip,
            'add_gripper': 'true',
        }.items(),
    )

    # 3) Nodo de control del gripper
    gripper_node = Node(
        package='gripper_control',
        executable='lite6_gripper_ws',
        name='lite6_gripper_ws',
        output='screen',
    )

    # 4) vr_bridge (ya como entry_point instalado, no como script suelto)
    vr_bridge = Node(
        package='foundation_pose_tf',
        executable='vr_bridge',
        name='vr_bridge',
        output='screen',
    )

    return LaunchDescription([
        robot_ip_arg,
        ros_ip_arg,
        tcp_endpoint,
        lite6_driver,
        gripper_node,
        vr_bridge,
    ])

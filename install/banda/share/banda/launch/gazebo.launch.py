"""Lanza Gazebo Classic con el robot 'banda' cargado y, opcionalmente, RViz."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg_share = get_package_share_directory('banda')
    gazebo_ros_share = get_package_share_directory('gazebo_ros')

    xacro_file = os.path.join(pkg_share, 'xacro', 'banda_transportadora.xacro')
    rviz_config = os.path.join(pkg_share, 'rviz', 'banda.rviz')
    test_box_urdf = os.path.join(pkg_share, 'urdf', 'test_box.urdf')

    # base_footprint queda a nivel de piso (z=0) y body_link/belt_link cuelgan
    # 0.728 m arriba de él (ver banda_transportadora.xacro). La superficie de
    # la banda (band.stl) está a su vez 0.003 m sobre el origen de belt_link
    # (z = 0.728 + 0.003 = 0.731). belt_surface_link (el cuerpo delgado y
    # dinámico que el plugin realmente mueve) tiene su cara SUPERIOR al ras
    # de ese mismo 0.731 y crece 2 cm hacia abajo (empotrado en la malla
    # real, invisible), así que el techo donde se apoyan los objetos sigue
    # siendo 0.731, no 0.731+espesor. Se suelta la caja un poco más arriba
    # para que caiga sobre la banda.
    band_top_z = 0.731
    box_half_size = 0.04
    drop_clearance = 0.05
    test_box_z = band_top_z + box_half_size + drop_clearance

    # Gazebo Classic no entiende el esquema "package://" (solo "model://"),
    # pero trata ambos igual si el directorio PADRE de "banda" está en
    # GAZEBO_MODEL_PATH: model://banda/meshes/x.stl -> <dir>/banda/meshes/x.stl
    gazebo_model_path = os.path.dirname(pkg_share)
    existing_model_path = os.environ.get('GAZEBO_MODEL_PATH', '')
    new_model_path = (
        gazebo_model_path + os.pathsep + existing_model_path
        if existing_model_path else gazebo_model_path
    )

    use_rviz = LaunchConfiguration('use_rviz')

    robot_description = ParameterValue(
        Command(['xacro ', xacro_file]), value_type=str)

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(gazebo_ros_share, 'launch', 'gazebo.launch.py')),
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': True,
        }],
    )

    spawn_entity = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        name='spawn_banda_transportadora',
        output='screen',
        arguments=[
            '-topic', 'robot_description',
            '-entity', 'banda_transportadora',
            '-timeout', '60',
        ],
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': True}],
        condition=IfCondition(use_rviz),
    )

    spawn_test_box = TimerAction(
        period=6.0,
        actions=[
            Node(
                package='gazebo_ros',
                executable='spawn_entity.py',
                name='spawn_test_box',
                output='screen',
                arguments=[
                    '-file', test_box_urdf,
                    '-entity', 'test_box',
                    '-x', '0', '-y', '0', '-z', str(test_box_z),
                ],
                condition=IfCondition(LaunchConfiguration('spawn_test_box')),
            ),
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_rviz', default_value='true',
            description='Lanzar también RViz junto a Gazebo'),
        DeclareLaunchArgument(
            'spawn_test_box', default_value='true',
            description='Soltar una caja de prueba sobre la banda para '
                        'verificar que el plugin de banda transportadora '
                        'la arrastra'),
        # En WSL2, el descubrimiento DDS por multicast falla intermitentemente
        # y spawn_entity.py nunca ve /spawn_entity aunque el servicio exista.
        # Forzar localhost evita ese problema.
        SetEnvironmentVariable('ROS_LOCALHOST_ONLY', '1'),
        SetEnvironmentVariable('GAZEBO_MODEL_PATH', new_model_path),
        # gzclient (OGRE) crashea con SIGSEGV bajo WSLg ("D3D12: Removing
        # Device") al usar el renderer 3D por defecto (basado en la GPU
        # virtual de WSLg). Forzar renderizado por software lo evita; es
        # más lento pero estable. Si tienes una GPU nativa configurada
        # correctamente en WSL2 y ya no ves el crash, puedes quitar esto.
        SetEnvironmentVariable('LIBGL_ALWAYS_SOFTWARE', '1'),
        gazebo,
        robot_state_publisher,
        spawn_entity,
        rviz,
        spawn_test_box,
    ])

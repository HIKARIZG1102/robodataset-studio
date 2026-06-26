from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


SUPPORTED_NUMERIC_MESSAGE_TYPES = {
    "std_msgs/msg/Bool",
    "std_msgs/msg/Float32",
    "std_msgs/msg/Float64",
    "std_msgs/msg/Int8",
    "std_msgs/msg/Int16",
    "std_msgs/msg/Int32",
    "std_msgs/msg/Int64",
    "std_msgs/msg/UInt8",
    "std_msgs/msg/UInt16",
    "std_msgs/msg/UInt32",
    "std_msgs/msg/UInt64",
    "std_msgs/msg/Float32MultiArray",
    "std_msgs/msg/Float64MultiArray",
    "std_msgs/msg/Int8MultiArray",
    "std_msgs/msg/Int16MultiArray",
    "std_msgs/msg/Int32MultiArray",
    "std_msgs/msg/Int64MultiArray",
    "std_msgs/msg/UInt8MultiArray",
    "std_msgs/msg/UInt16MultiArray",
    "std_msgs/msg/UInt32MultiArray",
    "std_msgs/msg/UInt64MultiArray",
    "geometry_msgs/msg/Point",
    "geometry_msgs/msg/PointStamped",
    "geometry_msgs/msg/Vector3",
    "geometry_msgs/msg/Vector3Stamped",
    "geometry_msgs/msg/Quaternion",
    "geometry_msgs/msg/QuaternionStamped",
    "geometry_msgs/msg/Pose",
    "geometry_msgs/msg/PoseStamped",
    "geometry_msgs/msg/Twist",
    "geometry_msgs/msg/TwistStamped",
    "geometry_msgs/msg/Wrench",
    "geometry_msgs/msg/WrenchStamped",
    "geometry_msgs/msg/Transform",
    "geometry_msgs/msg/TransformStamped",
    "sensor_msgs/msg/Imu",
    "nav_msgs/msg/Odometry",
}

STRING_MESSAGE_TYPES = {"std_msgs/msg/String"}


@dataclass
class MessageArrayResult:
    array: np.ndarray | None
    error: str = ""
    warning: str = ""


def is_supported_numeric_message_type(message_type: str) -> bool:
    return message_type in SUPPORTED_NUMERIC_MESSAGE_TYPES


def is_supported_generic_message_type(message_type: str) -> bool:
    return message_type in SUPPORTED_NUMERIC_MESSAGE_TYPES or message_type in STRING_MESSAGE_TYPES


def ros_message_to_array(msg: Any, message_type: str) -> MessageArrayResult:
    try:
        if message_type in STRING_MESSAGE_TYPES:
            return MessageArrayResult(np.array(str(getattr(msg, "data", ""))))
        if message_type in {
            "std_msgs/msg/Bool",
            "std_msgs/msg/Float32",
            "std_msgs/msg/Float64",
            "std_msgs/msg/Int8",
            "std_msgs/msg/Int16",
            "std_msgs/msg/Int32",
            "std_msgs/msg/Int64",
            "std_msgs/msg/UInt8",
            "std_msgs/msg/UInt16",
            "std_msgs/msg/UInt32",
            "std_msgs/msg/UInt64",
        }:
            return MessageArrayResult(np.asarray([getattr(msg, "data")], dtype=_scalar_dtype(message_type)))
        if "MultiArray" in message_type:
            data = list(getattr(msg, "data", []) or [])
            return MessageArrayResult(np.asarray(data, dtype=_multi_array_dtype(message_type)))
        values = _structured_values(msg, message_type)
        if values is not None:
            return MessageArrayResult(np.asarray(values, dtype=np.float32))
        return MessageArrayResult(None, error=f"unsupported ROS message type for dataset array conversion: {message_type}")
    except Exception as exc:
        return MessageArrayResult(None, error=f"failed to convert {message_type}: {exc}")


def message_type_to_stream_defaults(message_type: str, topic: str) -> dict[str, Any] | None:
    if not is_supported_generic_message_type(message_type):
        return None
    dtype = "str" if message_type in STRING_MESSAGE_TYPES else _default_dtype_name(message_type)
    return {
        "modality": _modality_for_type(message_type),
        "dtype": dtype,
        "shape": [],
        "training_role": "extension",
        "calvin_key": None,
        "required": False,
        "adapter": "generic_ros_message",
        "unsupported_policy": "error",
    }


def unsupported_message_type_warning(topic: str, message_type: str) -> str:
    return (
        f"topic {topic} has unsupported message type {message_type}; "
        "it will not be recorded until a converter is added"
    )


def _scalar_dtype(message_type: str) -> np.dtype:
    if message_type == "std_msgs/msg/Bool":
        return np.dtype(np.bool_)
    return np.dtype(_default_dtype_name(message_type))


def _multi_array_dtype(message_type: str) -> np.dtype:
    return np.dtype(_default_dtype_name(message_type))


def _default_dtype_name(message_type: str) -> str:
    if "Float32" in message_type:
        return "float32"
    if "Float64" in message_type:
        return "float64"
    if "Int8" in message_type:
        return "int8"
    if "Int16" in message_type:
        return "int16"
    if "Int32" in message_type:
        return "int32"
    if "Int64" in message_type:
        return "int64"
    if "UInt8" in message_type:
        return "uint8"
    if "UInt16" in message_type:
        return "uint16"
    if "UInt32" in message_type:
        return "uint32"
    if "UInt64" in message_type:
        return "uint64"
    if message_type == "std_msgs/msg/Bool":
        return "bool"
    return "float32"


def _modality_for_type(message_type: str) -> str:
    if message_type.startswith("geometry_msgs/msg/"):
        return "geometry"
    if message_type.startswith("sensor_msgs/msg/Imu"):
        return "imu"
    if message_type.startswith("nav_msgs/msg/Odometry"):
        return "odometry"
    if message_type.startswith("std_msgs/msg/"):
        return "scalar" if "MultiArray" not in message_type else "array"
    return "generic"


def _structured_values(msg: Any, message_type: str) -> list[float] | None:
    if message_type in {"geometry_msgs/msg/Point", "geometry_msgs/msg/Vector3"}:
        return _xyz(msg)
    if message_type in {"geometry_msgs/msg/PointStamped", "geometry_msgs/msg/Vector3Stamped"}:
        return _xyz(getattr(msg, "point", None) or getattr(msg, "vector", None))
    if message_type == "geometry_msgs/msg/Quaternion":
        return _xyzw(msg)
    if message_type == "geometry_msgs/msg/QuaternionStamped":
        return _xyzw(getattr(msg, "quaternion", None))
    if message_type == "geometry_msgs/msg/Pose":
        return [*_xyz(getattr(msg, "position", None)), *_xyzw(getattr(msg, "orientation", None))]
    if message_type == "geometry_msgs/msg/PoseStamped":
        return _structured_values(getattr(msg, "pose", None), "geometry_msgs/msg/Pose")
    if message_type == "geometry_msgs/msg/Twist":
        return [*_xyz(getattr(msg, "linear", None)), *_xyz(getattr(msg, "angular", None))]
    if message_type == "geometry_msgs/msg/TwistStamped":
        return _structured_values(getattr(msg, "twist", None), "geometry_msgs/msg/Twist")
    if message_type == "geometry_msgs/msg/Wrench":
        return [*_xyz(getattr(msg, "force", None)), *_xyz(getattr(msg, "torque", None))]
    if message_type == "geometry_msgs/msg/WrenchStamped":
        return _structured_values(getattr(msg, "wrench", None), "geometry_msgs/msg/Wrench")
    if message_type == "geometry_msgs/msg/Transform":
        return [*_xyz(getattr(msg, "translation", None)), *_xyzw(getattr(msg, "rotation", None))]
    if message_type == "geometry_msgs/msg/TransformStamped":
        return _structured_values(getattr(msg, "transform", None), "geometry_msgs/msg/Transform")
    if message_type == "sensor_msgs/msg/Imu":
        return [
            *_xyzw(getattr(msg, "orientation", None)),
            *_xyz(getattr(msg, "angular_velocity", None)),
            *_xyz(getattr(msg, "linear_acceleration", None)),
        ]
    if message_type == "nav_msgs/msg/Odometry":
        pose = getattr(getattr(msg, "pose", None), "pose", None)
        twist = getattr(getattr(msg, "twist", None), "twist", None)
        return [
            *(_structured_values(pose, "geometry_msgs/msg/Pose") or []),
            *(_structured_values(twist, "geometry_msgs/msg/Twist") or []),
        ]
    return None


def _xyz(value: Any) -> list[float]:
    return [float(getattr(value, key, 0.0) or 0.0) for key in ["x", "y", "z"]]


def _xyzw(value: Any) -> list[float]:
    return [float(getattr(value, key, 0.0) or 0.0) for key in ["x", "y", "z", "w"]]

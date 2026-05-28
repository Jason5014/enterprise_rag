"""配置基类"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional
import json


@dataclass
class BaseConfig:
    """配置基类，所有配置继承此类"""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，排除私有属性"""
        return {
            k: v
            for k, v in self.__dict__.items()
            if not k.startswith("_") and v is not None
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        """从字典创建配置"""
        # 过滤掉不在字段中的键
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_d = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered_d)

    def validate(self) -> bool:
        """验证配置合法性，子类可重写"""
        return True

    def merge(self, other: "BaseConfig") -> "BaseConfig":
        """合并两个配置，other的值会覆盖self的值"""
        if not isinstance(other, type(self)):
            raise TypeError(f"Cannot merge {type(self)} with {type(other)}")

        self_dict = self.to_dict()
        other_dict = other.to_dict()
        self_dict.update(other_dict)
        return type(self).from_dict(self_dict)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.to_dict()})"

    def to_json(self, indent: int = 2) -> str:
        """序列化为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, json_str: str):
        """从JSON字符串反序列化"""
        return cls.from_dict(json.loads(json_str))


@dataclass
class ConfigBundle:
    """配置束，封装一组相关配置"""

    retrieval: Optional[BaseConfig] = None
    answer: Optional[BaseConfig] = None
    pdf: Optional[BaseConfig] = None
    embedding: Optional[BaseConfig] = None
    eval_config: Optional[BaseConfig] = None
    indexer: Optional[BaseConfig] = None
    logging: Optional[BaseConfig] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {}
        for key, value in self.__dict__.items():
            if value is not None:
                if hasattr(value, "to_dict"):
                    result[key] = value.to_dict()
                else:
                    result[key] = value
        return result

    def get_config(self, name: str) -> Optional[BaseConfig]:
        """获取指定名称的配置"""
        return getattr(self, name, None)

    def update_config(self, name: str, config: BaseConfig) -> None:
        """更新指定名称的配置"""
        setattr(self, name, config)

    def __repr__(self) -> str:
        configs = [k for k, v in self.__dict__.items() if v is not None]
        return f"ConfigBundle({configs})"

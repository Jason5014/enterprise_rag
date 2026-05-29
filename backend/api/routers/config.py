"""配置管理路由 — 读取预设值、保存运行时覆盖"""
import copy
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.deps import get_current_user

ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()

# 内存中保存运行时覆盖（每次重启清空）
_runtime_overrides: Dict[str, Dict[str, Any]] = {}


def _retrieval_to_dict(rc) -> Dict[str, Any]:
    return {
        "chunk_size": rc.chunk_size,
        "chunk_overlap": rc.chunk_overlap,
        "top_k_retrieval": rc.top_k_retrieval,
        "enable_parent_retrieval": rc.enable_parent_retrieval,
        "enable_history": rc.enable_history,
        "enable_multiquery": rc.enable_multiquery,
        "enable_query_rewrite": rc.enable_query_rewrite,
        "enable_rerank": rc.enable_rerank,
        "rerank_top_k": rc.rerank_top_k,
        "use_jina_reranker": rc.use_jina_reranker,
        "fusion_method": rc.fusion_method,
        "bm25_weight": rc.bm25_weight,
        "rrf_k": getattr(rc, "rrf_k", 60),
    }


@router.get("/presets")
def get_presets(user=Depends(get_current_user)):
    """返回所有预设配置的默认参数值"""
    from config.presets import list_presets, get_preset
    result = {}
    for name in list_presets():
        try:
            preset = get_preset(name)
            if preset.retrieval:
                result[name] = _retrieval_to_dict(preset.retrieval)
        except Exception as e:
            logger.warning("读取预设 %s 失败: %s", name, e)
    return result


class OverridesBody(BaseModel):
    overrides: Dict[str, Any]


@router.patch("/presets/{preset_name}")
def save_overrides(
    preset_name: str,
    body: OverridesBody,
    user=Depends(get_current_user),
):
    """保存某个预设的运行时参数覆盖（内存，重启清空）"""
    _runtime_overrides[preset_name] = body.overrides
    return {"status": "ok", "preset": preset_name, "overrides": body.overrides}


@router.delete("/presets/{preset_name}/overrides")
def reset_overrides(preset_name: str, user=Depends(get_current_user)):
    """清除某个预设的运行时覆盖，恢复默认"""
    _runtime_overrides.pop(preset_name, None)
    return {"status": "ok"}


@router.get("/presets/{preset_name}/effective")
def get_effective(preset_name: str, user=Depends(get_current_user)):
    """返回叠加覆盖后的实际生效参数"""
    from config.presets import get_preset
    preset = get_preset(preset_name)
    base = _retrieval_to_dict(preset.retrieval) if preset.retrieval else {}
    overrides = _runtime_overrides.get(preset_name, {})
    return {**base, **overrides}


def get_runtime_overrides(preset_name: str) -> Dict[str, Any]:
    """供其他路由调用"""
    return _runtime_overrides.get(preset_name, {})

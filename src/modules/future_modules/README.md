# Future Modules / 未来扩展模块

Spain Assistant 架构支持按需接入新模块。每个模块放在 `src/modules/<module_name>/` 目录下，包含 `module.py` 暴露 `run()` 函数即可接入主调度器。

## 规划中的模块

| 模块名 | 描述 | 状态 |
|--------|------|------|
| `school_notice` | 学校通知解读（Agenda Escolar / colegios） | 规划中 |
| `family_events` | 马德里亲子活动推荐（文化、体育、博物馆） | 规划中 |
| `holiday_reminder` | 节日活动提醒（西班牙/马德里节假日） | 规划中 |
| `public_services` | 医疗/公共服务提醒（急诊、疫苗、市政预约） | 规划中 |
| `phrases_assistant` | 西语生活短句（就医、购物、学校、物业沟通） | 规划中 |
| `local_intel` | 区域生活情报（Madrid Norte、SSReyes、Alcobendas） | 规划中 |
| `daily_life` | 快递/餐厅/购物/物业沟通场景 | 规划中 |
| `calendar_ics` | 日历 ICS 事件生成（重要活动导入手机日历） | 规划中 |

## 如何新增模块

1. 在 `src/modules/<module_name>/` 创建目录
2. 实现 `module.py`，暴露 `run() -> dict` 函数
3. 在 `config.yaml` 的 `modules` 下添加配置项
4. 在 `src/main.py` 注册 CLI 命令和调度时间
5. 更新 `README.md` 说明新模块用法

## 模块接口规范

```python
# src/modules/<name>/module.py
def run() -> dict:
    """
    Returns:
        {
            "new_count": int,       # 本次处理条数
            "articles": list[dict], # 处理后的数据
            "errors": list[str],    # 错误信息（不影响整体运行）
        }
    """
    ...
```

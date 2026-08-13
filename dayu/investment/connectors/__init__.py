"""Investment 数据源连接器适配器。"""

from .source import (
    FinsSourceConnector,
    FinsWorkerGatewayProtocol,
    SourceConnectorProtocol,
    SourceConnectorRegistry,
)

__all__ = [
    "FinsSourceConnector",
    "FinsWorkerGatewayProtocol",
    "SourceConnectorProtocol",
    "SourceConnectorRegistry",
]

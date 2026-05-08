"""Demo tool: echo a message back. Smallest end-to-end example of the @tool contract."""
from __future__ import annotations

from pydantic import BaseModel

from shared.core import tool


class EchoArgs(BaseModel):
    message: str


class EchoData(BaseModel):
    echoed: str
    length: int


@tool(
    name="echo",
    version="1.0.0",
    description="Echo a message back, returning its length too.",
    args_schema=EchoArgs,
    data_schema=EchoData,
    side_effects=False,
)
def echo(args: EchoArgs) -> EchoData:
    return EchoData(echoed=args.message, length=len(args.message))

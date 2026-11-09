import asyncio
import os
import sys
import time
from collections import defaultdict, deque
from pathlib import Path
import jwt
import jsonschema
from fastapi import HTTPException
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.core.config import settings
from app.schemas import ToolEnvelope
from app.security.policy import require
from app.mcp.registry import TOOLS, SERVERS

rates = defaultdict(deque)
concurrency = asyncio.Semaphore(8)


def check_rate(user_id):
    current = time.monotonic()
    bucket = rates[user_id]
    while bucket and bucket[0] < current - 60:
        bucket.popleft()
    if len(bucket) >= 30:
        raise HTTPException(429, 'Tool rate limit exceeded')
    bucket.append(current)


async def invoke(user, name, arguments):
    definition = TOOLS.get(name)
    if not definition or definition['server'] not in SERVERS:
        raise HTTPException(403, 'Unapproved tool or server')
    require(user, definition['permission'])
    check_rate(user.id)
    ticket = jwt.encode({'sub': user.id, 'org': user.org_id, 'tool': name,
                         'iat': int(time.time()), 'exp': int(time.time()) + 30,
                         'iss': settings.issuer, 'aud': 'banking-mcp'}, settings.jwt_secret, algorithm='HS256')
    # Environment is constructed, not inherited wholesale: no provider keys enter the server.
    env = {key: os.environ[key] for key in ['SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP'] if key in os.environ}
    # Serverless runtimes add vendored dependency directories to the parent path.
    # Preserve those trusted runtime paths so the STDIO child can import the SDK.
    runtime_paths = [str(Path(__file__).resolve().parents[2])] + [path for path in sys.path if path and Path(path).is_dir()]
    env.update({'PYTHONPATH': os.pathsep.join(dict.fromkeys(runtime_paths)), 'DATABASE_URL': settings.database_url,
                'JWT_SECRET': settings.jwt_secret, 'BANK_MCP_TICKET': ticket, 'POLICY_VERSION': settings.policy_version})
    params = StdioServerParameters(command=sys.executable, args=['-m', 'app.mcp.server', definition['server']], env=env)
    try:
        async with concurrency, asyncio.timeout(30):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    initialization = await session.initialize()
                    if initialization.serverInfo.name != 'banking-' + definition['server']:
                        raise ValueError('Unexpected server identity')
                    discovered = await session.list_tools()
                    tool = next((tool for tool in discovered.tools if tool.name == name), None)
                    if not tool or not tool.outputSchema:
                        raise ValueError('Required typed tool absent')
                    jsonschema.validate(arguments, tool.inputSchema)
                    result = await session.call_tool(name, arguments)
                    if result.isError or result.structuredContent is None:
                        raise ValueError('MCP tool rejected request')
                    jsonschema.validate(result.structuredContent, tool.outputSchema)
                    return ToolEnvelope.model_validate(result.structuredContent).model_dump()
    except TimeoutError:
        raise HTTPException(504, 'MCP timeout; inspect instruction status before retrying') from None
    except Exception:
        raise HTTPException(502, 'MCP operation failed; inspect audit history before retrying') from None

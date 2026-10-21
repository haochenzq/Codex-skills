import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import project_server as app


async def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root/'AGENTS.md').write_text('规则一\n规则二\n', encoding='utf-8')
        (root/'credentials.txt').write_text('dummy', encoding='utf-8')
        with patch.object(app, 'ROOT', root):
            assert app.read_project_file('AGENTS.md', 2, 1)['lines'][0]['text'] == '规则二'
            for bad in ('../AGENTS.md', 'C:/Windows/win.ini', 'AGENTS.md:stream', 'credentials.txt'):
                try:
                    app.read_project_file(bad)
                    raise AssertionError('Boundary bypass')
                except ValueError:
                    pass
            (root/'notes.txt').write_text('api_key = ' + 'sk-' + 'x'*30, encoding='utf-8')
            assert app.read_project_file('notes.txt')['lines'][0]['text'] == '[已屏蔽疑似凭据行]'
            assert len(app.search_project_files('规则')['matches']) == 2
            (root/'AGENTS.md').write_text('最新内容', encoding='utf-8')
            assert app.read_project_file('AGENTS.md')['lines'][0]['text'] == '最新内容'
        with patch.object(app, 'VIDEO_ROOT', root):
            assert app.read_project_file('视频制作/AGENTS.md')['lines'][0]['text'] == '最新内容'
            assert app.list_project_files('视频制作')['items']
            assert app.search_project_files('最新', '视频制作')['matches'][0]['path'] == '视频制作/AGENTS.md'
            for bad in ('视频制作/../学习提升/AGENTS.md', '视频制作/C:/Windows/win.ini', '视频制作/credentials.txt'):
                try:
                    app.checked(bad)
                    raise AssertionError('Cross-project boundary bypass')
                except ValueError:
                    pass
    params = StdioServerParameters(command=sys.executable, args=[str(Path(app.__file__))])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            assert {t.name for t in tools} == {'list_project_files','read_project_file','search_project_files'}
            assert all(t.annotations.read_only_hint for t in tools)
            result = await session.call_tool('read_project_file', {'path':'AGENTS.md','max_lines':3})
            assert not result.is_error
            denied = await session.call_tool('write_file', {})
            assert denied.is_error
    print('PASS: boundaries, redaction, live reread, line ranges, search, MCP read-only tools')


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(),30))

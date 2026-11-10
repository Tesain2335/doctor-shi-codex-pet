"""Read per-turn API receipts, containing usage numbers and IDs only."""
import json
import os
from pathlib import Path
import uuid


def canonical_uuid(value):
    try:return str(uuid.UUID(value)) if isinstance(value,str) else None
    except ValueError:return None


class DeepSeekUsage:
    def __init__(self,root=None):
        self.root=Path(root) if root is not None else Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'deepseek/usage'

    def total_for(self,context):
        if not isinstance(context,dict):return None,True
        thread=canonical_uuid(context.get('thread_id'));turn=canonical_uuid(context.get('turn_id'))
        if not thread or not turn:return None,True
        total=0;incomplete=False;seen={}
        folder=self.root/thread/turn
        try:
            # Stable ordering also makes conflicting duplicate receipts deterministic.
            for path in sorted(folder.glob('*.json'),key=lambda p:p.name):
                try:
                    record=json.loads(path.read_text(encoding='utf-8'))
                    if (canonical_uuid(record.get('thread_id'))!=thread or
                            canonical_uuid(record.get('turn_id'))!=turn):
                        incomplete=True;continue
                    call=canonical_uuid(record.get('call_id'));value=record.get('total_tokens')
                    if not call or type(value) is not int or value<0:
                        incomplete=True;continue
                    if call in seen:
                        if seen[call]!=value:incomplete=True
                        continue
                    seen[call]=value;total+=value
                except (OSError,ValueError,AttributeError,TypeError):incomplete=True
        except OSError:incomplete=True
        return total,incomplete

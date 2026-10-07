"""فقط مدل جعلی برای ارائه و تست حلقهٔ واقعی LangChain؛ هیچ API فراخوانی نمی‌شود."""
import json
from uuid import uuid4
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class DemoModel(BaseChatModel):
    @property
    def _llm_type(self):
        return 'demo-no-api'

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        recent = []
        for message in reversed(messages):
            if message.type == 'human':
                break
            recent.insert(0, message)
        results = {m.name: json.loads(m.content) for m in recent if isinstance(m, ToolMessage)}
        name, args = 'read_case', {}
        if 'apply_change' in results:
            answer = AIMessage(content='DEMO: نتیجهٔ ابزار ثبت شد: ' + json.dumps(results['apply_change'], ensure_ascii=False))
        else:
            if 'draft_reply' in results:
                draft = results['draft_reply']
                if 'error' in draft:
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content='DEMO stopped: ' + draft['error']))])
                name, args = 'apply_change', {'proposal_id': draft['id']}
            elif 'search_docs' in results:
                case = results['read_case']
                known = case['facts']
                if not known.get('streamlit_version'):
                    question, field = 'نسخهٔ Streamlit محیطی که خطا دارد چیست؟', 'streamlit_version'
                    reason = 'برای مقایسه با مستندات و تغییرات نسخه‌ها لازم است.'
                    decision = 'ask'
                elif not known.get('location'):
                    question, field = 'همین برنامه در محیط محلی هم مشکل دارد یا فقط روی سرور؟', 'location'
                    reason = 'پاسخ، تفاوت محیط استقرار و رفتار برنامه را جدا می‌کند.'
                    decision = 'ask'
                else:
                    question, field = 'علت قطعی مشخص نیست؛ پرونده با اطلاعات موجود به نگه‌دارنده ارجاع شود.', ''
                    reason, decision = 'اطلاعات موجود برای ادعای راه‌حل کافی نیست.', 'escalate'
                name = 'draft_reply'
                args = dict(reply=question + '\n' + reason, decision=decision, reason=reason,
                            unknowns=[field or 'root_cause'], source_ids=[], question_field=field)
            elif 'read_case' in results:
                name, args = 'search_docs', {'query': results['read_case']['title']}
            answer = AIMessage(content='', tool_calls=[dict(name=name, args=args, id=uuid4().hex, type='tool_call')])
        return ChatResult(generations=[ChatGeneration(message=answer)])

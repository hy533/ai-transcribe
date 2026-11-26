import pytest

from summarize import stream_summary, strip_think

pytestmark = pytest.mark.live

ZH_SAMPLE = """大家好，今天我想聊聊为什么大多数人的个人知识管理会失败。很多人一开始热情很高，装了很多笔记软件，建立了复杂的标签体系，但是三个月之后就放弃了。原因其实很简单：他们把精力花在了整理上，而不是使用上。我自己的经验是，笔记的价值不在于存了多少，而在于你能不能在需要的时候找到并用起来。所以我建议大家做三件事。第一，记录的时候只写一句话的结论，不要抄原文。第二，每周固定留二十分钟回顾，把真正有用的内容挑出来，其余的直接忽略。第三，每个月至少用一次笔记里的内容去写一篇短文或者做一个小项目，让知识真正流动起来。如果你只是想收藏好看的文章，那这套方法可能不适合你；但如果你希望把阅读变成实际的产出，比如写作者、研究人员或者需要持续学习的工程师，不妨从下周开始试一试。"""

EN_SAMPLE = """Hi everyone. Today I want to talk about why most home coffee setups disappoint people. They buy an expensive machine, follow a video, and still end up with bitter, thin espresso. The machine is rarely the problem. In my experience, three things matter far more than hardware. First, the grinder: a cheap blade grinder produces uneven particles, so some grounds over-extract while others barely get touched. Second, freshness: beans older than about six weeks lose most of their aromatics, and no technique can bring them back. Third, measurement: weigh your dose and your output, and change only one variable at a time. I tested this over two months with the same cheap machine and a decent hand grinder, and the improvement was dramatic. If you already own a high-end grinder and fresh beans, this talk will not teach you much. But if you are a beginner frustrated with your results, or someone about to spend a lot on a new machine, it may save you real money."""


def cjk_ratio(s):
    return sum("一" <= c <= "鿿" for c in s) / max(len(s), 1)


def test_live_chinese_summary_is_chinese():
    out = strip_think("".join(stream_summary(ZH_SAMPLE, "zh")))
    assert cjk_ratio(out) > 0.3


def test_live_english_summary_is_english():
    out = strip_think("".join(stream_summary(EN_SAMPLE, "en")))
    assert cjk_ratio(out) < 0.02

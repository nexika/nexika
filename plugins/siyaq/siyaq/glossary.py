"""A small English-Arabic glossary of software and business words, applied when the index is built.

Each section gets the other language's words for the terms it uses, so an Arabic question finds
English docs ("كيف نعمل تراجع للإصدار" -> Rollback) and an English one finds Arabic docs. Only
words with one clear meaning in a codebase are listed; anything else is better written as
`keywords` in a hand-written entry (/siyaq:add).
"""
from __future__ import annotations

from . import text

# english words (any form) | arabic words (any form)
PAIRS = """
rollback roll-back revert | تراجع ارجاع استرجاع
deploy deployment deploys | نشر
release releases | اصدار
environment environments | بيئه
staging | تجريبي
production | انتاج
test tests testing | اختبار
migration migrations migrate | ترحيل
database | قاعده بيانات
secret secrets | سر اسرار
invoice invoices | فاتوره فواتير
issued issue | اصدار
edit edited modify | تعديل
discount discounts | خصم
coupon coupons voucher | كوبون قسيمه
payment payments pay | دفع
order orders | طلب طلبات
cart | سله
product products | منتج منتجات
customer customers client | عميل عملاء
price pricing | سعر تسعير
tax taxes | ضريبه
refund refunds | استرداد
shipping | شحن
inventory stock | مخزون
subscription subscriptions | اشتراك
account accounts | حساب
user users | مستخدم مستخدمين
permission permissions | صلاحيه صلاحيات
login sign-in | دخول
password passwords | كلمه مرور
authentication | مصادقه
authorization | تفويض
email emails | بريد
notification notifications | اشعار اشعارات
error errors bug bugs | خطا اخطاء
log logs logging | سجل سجلات
cache caching | كاش تخزين مؤقت
server servers | خادم
branch branches | فرع
merge merges | دمج
review reviews | مراجعه
build builds | بناء
install installation | تثبيت
config configuration settings | اعدادات
performance | اداء
security | امان
report reports | تقرير تقارير
search | بحث
upload uploads | رفع
download downloads | تنزيل
delete deletion | حذف
backup backups | نسخ احتياطي
queue queues | طابور
schedule scheduled | جدوله
translation translations | ترجمه
language languages | لغه
currency | عمله
"""


def _build() -> dict[str, set[str]]:
    table: dict[str, set[str]] = {}
    for line in PAIRS.strip().splitlines():
        english, _, arabic = line.partition("|")
        en = set(text.tokens(english.replace("-", " ")))
        ar = set(text.tokens(arabic))
        for token in en:
            table.setdefault(token, set()).update(ar)
        for token in ar:
            table.setdefault(token, set()).update(en)
    return table


TABLE = _build()


def other_language(tokens: list[str]) -> list[str]:
    """The glossary words of the other language for these tokens (each once)."""
    out: dict[str, None] = {}
    for token in dict.fromkeys(tokens):
        for word in sorted(TABLE.get(token, ())):
            if word not in tokens:
                out[word] = None
    return list(out)

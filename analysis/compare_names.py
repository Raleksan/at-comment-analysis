"""Cross-reference book names with comment mentions and POV guesses.

Classifies every proper name from the book (analysis/book_names.csv):
- eliminated          guessed as the POV character before Jun 9 (author: wrong)
- live_guess          guessed only after the author's Jun 9 "nobody guessed"
- mentioned_not_guessed  appears in comments since Feb 27, never bet as POV
- never_mentioned     in the book, absent from comments entirely

Writes analysis/book_vs_comments.csv and prints the candidate pool.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from namelib import Lemmatizer

BOOK_CSV = Path("analysis/book_names.csv")
COMMENTS_CSV = Path("analysis/names_since_feb27.csv")
OUT_CSV = Path("analysis/book_vs_comments.csv")

# POV guesses curated from analysis/pov_threads.txt (see pov_name_report.md).
# Surface forms; lemmatized below so they match both extractions.
GUESSED_PRE_JUN9 = """
Нора Райхан Леон Цвай Добряк Кроцеа Морс Морген Хейли Сказочник Иксор Ридл
Озпин Озма Пенни Сапфир Пугало Паук Салем Кроу Таянг Рэйвен Аземи Сафрон
Синдер Грей Спрюс Уиллис Вайс Винтер Рома Роман Торчвик Нео Вайолет
Доброведьма Ирис Рокс Холмс Шерлок Руби Саммер Иссоп Манье Цугнум Фабий
Пенат Гусь Кали Белладонна Гира Блейк Адам Сиенна Илия Эмбер Ворон Король
Льюис Алиса Жанна Аш Сильвер Гарнет Стронг Йоланд Блу Редсмит Базиль Хорус
Аксиманд Жалость Похоть Виллоу Терри
""".split()

GUESSED_POST_JUN9 = """
Ахил Бронзвинг Валуа Аларик Вельвет Легионер Лаванда
""".split()


def main() -> int:
    book = pd.read_csv(BOOK_CSV, encoding="utf-8-sig")
    comments = pd.read_csv(COMMENTS_CSV, encoding="utf-8-sig")

    lemmatize = Lemmatizer()
    pre = {lemmatize(w)[0] for w in GUESSED_PRE_JUN9}
    post = {lemmatize(w)[0] for w in GUESSED_POST_JUN9}
    comment_mentions = {
        str(row.name_l): int(row.mentions)
        for row in comments.assign(name_l=comments.name.str.lower()).itertuples()
    }

    def classify(lemma: str) -> str:
        if lemma in pre:
            return "eliminated"
        if lemma in post:
            return "live_guess"
        if lemma in comment_mentions:
            return "mentioned_not_guessed"
        return "never_mentioned"

    book["lemma"] = book.name.str.lower()
    book["status"] = book.lemma.map(classify)
    book["comment_mentions"] = book.lemma.map(comment_mentions).fillna(0).astype(int)
    out = book.drop(columns=["lemma"]).sort_values("mentions", ascending=False)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(out.status.value_counts().to_string(), file=sys.stderr)
    print(f"-> {OUT_CSV}", file=sys.stderr)

    pool = out[out.status.isin(["never_mentioned", "mentioned_not_guessed"])]
    cols = ["name", "mentions", "comment_mentions", "status", "name_pos", "first_pct"]
    print("\n=== Candidate pool: top book names nobody bet on ===")
    print(pool.head(60)[cols].to_string(index=False))
    print("\n=== Live guesses (made after Jun 9) present in the book ===")
    print(out[out.status == "live_guess"][cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

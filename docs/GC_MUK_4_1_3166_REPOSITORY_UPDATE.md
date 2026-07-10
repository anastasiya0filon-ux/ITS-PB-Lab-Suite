# GC МУК 4.1.3166 — обновление репозитория

Это не установщик. Архив нужно распаковать поверх корня репозитория
ITS-PB-Lab-Suite с заменой файлов.

Добавляется полноценный каталог:

app/modules/GC/
- gc_generator.py
- data/MUK_4_1_3166.json
- data/gc_muk_4_1_3166_calibration_model.json
- excel_templates/GC_MUK_4_1_3166_RANDOM.xlsx
- excel_templates/GC_MUK_4_1_3166_ACTUAL.xlsx

Актуальный app/main.pyw уже содержит:
- раздел GC в боковом меню;
- четыре режима генерации;
- постоянную таблицу компонентов;
- две колонки для фактических значений;
- подключение массовых шаблонов.

Результат на один шифр:
- 2 хроматограммы;
- для каждой отдельные PNG ПИД-1 и ПИД-2;
- generation.json;
- peaks.csv.

Проверка:
1. python app\main.pyw
2. Открыть GC.
3. Одиночная — рандом.
4. Сформировать хроматограммы.
5. Проверить app\modules\GC\output\<шифр>.

После проверки:
git add app/main.pyw app/modules/GC "ITS-PB Lab Suite.spec" docs/GC_MUK_4_1_3166_REPOSITORY_UPDATE.md
git commit -m "Add GC MUK 4.1.3166 module"
git push

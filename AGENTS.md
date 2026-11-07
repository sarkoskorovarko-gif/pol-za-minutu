# «Пол за минуту» — основной сайт

Знания проекта для Codex, Kimi и Claude. Claude — ведущий (решает, правит, коммитит), Kimi — руки (черновики, проверки), Codex — напарник (думает, проверяет работу Claude). Пользователю — по-русски, просто, коротко. Файлы правит только Claude, если не договорились иначе.

## Что это
Статический сайт (GitHub Pages, репозиторий pol-za-minutu): клиент выбирает декор ламината EGGER (108 декоров) и видит его в настоящих комнатах днём и вечером, считает материалы и раскладку.
Отдельная копия для сети дверей «Юркас» — D:\yurkas (свой AGENTS.md, не публикуется, двери — только там).

## Устройство
- index.html, style.css, app.js, calc.js, layout.js, sw.js. При любой правке поднять `?v=` в index.html и VERSION/FILES в sw.js.
- data/rooms.json — у каждой комнаты флаги ['', 'night/', 'x/', 'x/night/']; data/<комната>/… — картинки по декорам.
- Рендер комнат (tools/interior: run_full.py, build.py, grade.py, floor_match.py, ai_check.py, publish_living.py; tools/blender: ai_realism, floor_tex, floor_render, floor_composite): run_full.py → build.py → ai_realism (одна нейросетевая основа на комнату) → floor_tex/floor_render → floor_composite → grade → floor_match → ai_check. Публикация: publish_living.py <папка> night --room <комната>. Тяжёлое (Blender, ComfyUI, модели) — в D:\pol-ai.
- Двери (для Юркаса): tools/blender/door_model.py (полотно из фото ×4 + маска стекла), door_check.py --photo (автопроверка с фото каталога), door_upscale.py, door_layer.py, door_match.py, спецификации tools/blender/doors/*.json.

## Правила
- Перед коммитом — reviewer. Push на GitHub только с согласия пользователя.
- Ничего не удалять без списка и слова «удаляй». Пароли и ключи не вводить.
- Не придумывать названий; тексты для клиента простыми словами. Перед показом — проверка, с ошибками не показывать.

## Состояние (2026-11-07)
- v78: кухня вечером без лишних выключателей, правки по проверке Kimi. Все коммиты после origin/main (c966225, 0ad43af, 1bf42ff, 6b485e4, 55c001e) не отправлены на GitHub — ждут «да».
- Презентация для директора EGGER Беларусь (claude.ai, Slides): главное — ламинат; на слайде контактов пустые места под ссылки и имя/телефон.

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

## Работа без Claude (Codex или Kimi сами)
Только по прямому решению пользователя — тогда Codex/Kimi правят файлы и коммитят сами (это снимает правило «правит только Claude»).
Запуск в этой папке: `codex -s workspace-write "Прочитай AGENTS.md и docs/agents/*.md, задача: ..."` или `kimi` (интерактивно, правки подтверждает пользователь).
Подробные инструкции — `docs/agents/`:
- `interior.md` — рендер комнат: порядок, уроки, где что лежит (Blender `D:\pol-ai\blender\blender.exe`, ComfyUI `D:\pol-ai\comfyui`).
- `reviewer.md` — проверка перед коммитом; `critic.md` + `realism-criteria.md` — оценка рендера перед показом; `worker.md` — массовые прогоны. Выполнять их как чек-листы самому (это роли помощников Claude).
Порядок любой задачи: 1) прочитать нужный файл из docs/agents; 2) сделать; 3) проверить (тесты, ai_check, осмотр краёв кадра крупно); 4) пройти reviewer.md по своему диффу; 5) коммит с `git -c user.name=sarkoskorovarko-gif -c user.email=sarkoskorovarko@gmail.com commit`; 6) записать итог в «Состояние» выше.
Двери: `python tools/blender/door_upscale.py <имя>` (фото D:/pol-ai/doors/<имя>.jpg → 4x/), спецификация `tools/blender/doors/<имя>.json` (по образцу соседних), проверка `python tools/blender/door_check.py <имя> --photo` — все пункты должны быть ВЕРНО. Новая дверь в комнаты Юркаса (без Blender, полы не трогаем), для каждой пары папок:
  гостиная день `D:/pol-ai/door_test` → `D:/yurkas/data/living_door`; вечер `D:/pol-ai/door_night` → `.../living_door/night`; спальня `D:/pol-ai/bed_door` → `D:/yurkas/data/bedroom_door`:
  1) `python tools/blender/door_relayer.py <папка рендера> <имя>` — слой двери; 2) `python tools/blender/door_match.py <папка рендера> <папка Юркаса>` — цвет под комнату;
  3) только для вечера гостиной: door_match перезаписал ВСЕ слои дверей, поэтому сразу после него один раз `python D:/yurkas/tools/warm_evening.py D:/yurkas/data/living_door/night/door_*.png` (картинки полов *.jpg не трогать — они уже тёплые);
  4) добавить дверь в `D:/yurkas/data/doors.json`, поднять версию, наложить слой на картинку комнаты и посмотреть глазами.
Нельзя без пользователя: push, удаление, публикация, ввод паролей/ключей. Если не уверен — спросить пользователя, а не гадать.

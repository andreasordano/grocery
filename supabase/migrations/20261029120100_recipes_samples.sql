-- WEB-53: 24 sample dinners for the recipes table, drafted with AI (Claude, in a development session, 29 Oct 2026)
-- for Estonian home cooking. They arrive as drafts: read each one in /admin.html (and cook it if you can) before
-- publishing it. Priced on 29 Oct at Rimi and Barbora (Selver and Prisma don't answer from abroad): every one can be
-- bought completely at one store at least. ON CONFLICT DO NOTHING: running this again never overwrites edits.
INSERT INTO recipes (id, name, about, method, emoji, servings, minutes, ingredients, pantry, tags, months, notes) VALUES
('pr-kalafilee-rukkipaneeringus', 'Kalafilee rukkipaneeringus kartulipudruga', 'White fish fried in rye flour, with buttery mashed potatoes and sour cream. Plain Estonian home cooking.', '1. Peel the potatoes and boil them in salted water for about 20 minutes, then mash with butter and a splash of milk.
2. Salt the fish and press both sides into the rye flour.
3. Fry them in hot oil, 2–3 minutes a side, until golden.
4. Serve with the mash, sour cream and chopped dill.', '🐟', 2, 30, ARRAY['400 g tursafilee', '600 g kartul', 'rukkijahu', '200 g hapukoor', 'till']::text[], ARRAY['või', 'piim', 'sool', 'pipar', 'õli']::text[], ARRAY['fish']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-tatar-seente-ja-sibulaga', 'Tatar seente ja sibulaga', 'Buckwheat with fried mushrooms, onion and sour cream: cheap, filling and ready in 25 minutes.', '1. Rinse the buckwheat and cook it in 400 ml salted water, covered, for about 15 minutes.
2. Meanwhile fry the sliced mushrooms and chopped onion in butter until golden.
3. Stir the mushrooms into the buckwheat, season, and serve with sour cream.', '🍄', 2, 25, ARRAY['200 g tatar', '400 g šampinjonid', '150 g sibul', '200 g hapukoor']::text[], ARRAY['või', 'sool', 'pipar']::text[], ARRAY['veggie']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-kanakarri-riisiga', 'Kanakarri riisiga', 'Chicken in a mild coconut curry with rice. A weeknight favourite that needs one pan.', '1. Cook the rice as the pack says.
2. Fry the chopped onion in oil, add the curry paste and fry for a minute.
3. Add the chicken in strips and the sliced pepper, and fry for 5 minutes.
4. Pour in the coconut milk and simmer for 10 minutes. Season and serve with the rice.', '🍛', 2, 30, ARRAY['400 g kanafilee', '200 g basmati riis', '400 ml kookospiim', '150 g sibul', '200 g paprika', 'karripasta']::text[], ARRAY['õli', 'küüslauk', 'sool']::text[], ARRAY['chicken', 'rice']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-lohepasta-koorekastmes', 'Lõhepasta koorekastmes', 'Pasta with salmon, spinach and lemon in a light cream sauce.', '1. Boil the pasta in salted water.
2. Cut the salmon into cubes and fry it briefly in oil with chopped garlic.
3. Add the cream and spinach and simmer until the spinach wilts, then add lemon juice, salt and pepper.
4. Toss with the drained pasta.', '🍝', 2, 25, ARRAY['250 g pasta', '300 g lõhefilee', '200 ml vahukoor', '100 g beebispinat', '1 tk sidrun']::text[], ARRAY['küüslauk', 'õli', 'sool', 'pipar']::text[], ARRAY['fish', 'pasta']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-pelmeenid-hapukoore-ja-tilliga', 'Pelmeenid hapukoore ja tilliga', 'Pelmeni from the freezer, boiled and served with sour cream and dill. The 15-minute dinner many grew up on.', '1. Bring a big pot of salted water to the boil with a bay leaf.
2. Add the frozen pelmeni, stir, and cook as the pack says (about 7 minutes after they float).
3. Drain, toss with a little butter, and serve with sour cream and dill.', '🥟', 2, 15, ARRAY['800 g pelmeenid', '200 g hapukoor', 'till']::text[], ARRAY['sool', 'loorberileht', 'või']::text[], ARRAY['meat']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-pesto-pasta-kirsstomatitega', 'Pesto-pasta kirsstomatitega', 'Pasta with green pesto, cherry tomatoes and mozzarella. Hardly cooking at all.', '1. Boil the pasta in salted water.
2. Halve the tomatoes and tear the mozzarella.
3. Toss the drained pasta with the pesto and a spoon of the cooking water, then add the tomatoes and mozzarella.', '🍅', 2, 15, ARRAY['250 g pasta', 'pesto', '250 g kirsstomatid', '125 g mozzarella']::text[], ARRAY['oliiviõli', 'sool', 'pipar']::text[], ARRAY['pasta', 'veggie']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-praetud-riis-kanaga', 'Praetud riis kana ja köögiviljadega', 'Fried rice with chicken, frozen vegetables and egg. Best with yesterday''s rice.', '1. Cook the rice and let it cool, or use rice cooked the day before.
2. Fry the chicken strips in a hot pan, add the vegetables and fry for 5 minutes.
3. Push everything aside, scramble the eggs in the pan, then add the rice.
4. Fry for a few minutes more and season with soy sauce.', '🍳', 2, 25, ARRAY['200 g riis', '300 g kanafilee', '400 g köögiviljasegu', '2 tk munad', 'sojakaste']::text[], ARRAY['õli', 'küüslauk', 'sool']::text[], ARRAY['rice', 'chicken']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-korvitsasupp', 'Kõrvitsasupp', 'A smooth autumn pumpkin soup with ginger and cream, topped with pumpkin seeds.', '1. Peel the pumpkin and carrots and cut them into cubes.
2. Soften the chopped onion and grated ginger in oil.
3. Add the vegetables, a stock cube and water to cover, and simmer for 20 minutes.
4. Blend until smooth, stir in the cream and season. Serve with toasted pumpkin seeds.', '🎃', 4, 40, ARRAY['1 kg kõrvits', '300 g porgand', '150 g sibul', 'ingver', '200 ml vahukoor', 'kõrvitsaseemned']::text[], ARRAY['õli', 'puljongikuubik', 'sool', 'pipar']::text[], ARRAY['soup', 'veggie']::text[], ARRAY[9, 10, 11]::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-lohesupp-koorega', 'Lõhesupp koorega', 'A creamy Nordic salmon soup with potatoes and plenty of dill.', '1. Bring 1 litre of water to the boil with salt and a bay leaf.
2. Add the diced potatoes, carrots and sliced leek, and cook for 15 minutes.
3. Add the salmon in cubes and the cream, and simmer gently for 5 minutes.
4. Season and add lots of chopped dill.', '🐟', 4, 35, ARRAY['400 g lõhefilee', '600 g kartul', '200 g porgand', 'porrulauk', '200 ml vahukoor', 'till']::text[], ARRAY['või', 'loorberileht', 'sool', 'pipar']::text[], ARRAY['soup', 'fish']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-frikadellisupp', 'Frikadellisupp', 'Clear soup with small meatballs, potatoes and carrot. Estonian home cooking at its plainest.', '1. Bring 1.5 litres of salted water to the boil with a bay leaf.
2. Add the diced potatoes, carrot and onion, and cook for 10 minutes.
3. Mix the mince with an egg, salt and pepper, roll small balls with wet hands and drop them in.
4. Simmer for 10 minutes more, until the meatballs are cooked through. Add dill.', '🍲', 4, 40, ARRAY['400 g hakkliha', '600 g kartul', '200 g porgand', '100 g sibul', 'till']::text[], ARRAY['muna', 'loorberileht', 'sool', 'pipar']::text[], ARRAY['soup', 'meat']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-soljanka', 'Soljanka', 'A sour, smoky meat soup with pickles, olives and lemon, made in a big pot for a crowd.', '1. Fry the chopped onion in oil in a big pot, then the sliced sausages for a few minutes.
2. Add the tomato paste and the diced pickles, then 2 litres of water and a bay leaf.
3. Simmer for 20 minutes, then add the olives and a splash of the pickle brine.
4. Serve with a slice of lemon and a spoon of sour cream.', '🥣', 6, 60, ARRAY['300 g suitsuvorst', '300 g viinerid', '300 g hapukurgid', '150 g sibul', 'tomatipasta', 'oliivid', '1 tk sidrun', '200 g hapukoor']::text[], ARRAY['õli', 'loorberileht', 'pipar']::text[], ARRAY['soup', 'meat', 'friends']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-hernesupp-suitsulihaga', 'Hernesupp suitsulihaga', 'Thick pea soup with smoked pork, eaten on Shrove Tuesday (vastlapäev) before going sledging.', '1. Soak the peas overnight, then rinse them.
2. Cover the peas and the smoked ribs with 2.5 litres of water and simmer for about an hour, skimming.
3. Lift out the ribs, cut off the meat and put it back.
4. Add the diced potatoes, carrot and onion and cook for 20 minutes more. Season.', '🫛', 6, 120, ARRAY['400 g poolitatud herned', '600 g suitsuribid', '400 g kartul', '200 g porgand', '150 g sibul']::text[], ARRAY['loorberileht', 'sool', 'pipar']::text[], ARRAY['soup', 'meat']::text[], ARRAY[2]::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-mulgipuder-peekoniga', 'Mulgipuder peekoniga', 'Mashed potato and barley with crispy bacon and onion: Estonia''s national dish, from Mulgimaa.', '1. Rinse the barley and simmer it in 500 ml water for 20 minutes.
2. Add the peeled, cubed potatoes and water to cover, and cook until soft, about 20 minutes.
3. Drain and mash together with butter and salt.
4. Fry the bacon and onion until crisp and spoon them on top. Serve with a glass of kefir.', '🥔', 4, 60, ARRAY['1 kg kartul', '150 g odrakruup', '200 g peekon', '150 g sibul', 'keefir']::text[], ARRAY['või', 'sool']::text[], ARRAY['meat']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-verivorst-pohlamoosiga', 'Verivorst pohlamoosiga', 'Blood sausage baked until crisp, with roast potatoes, sauerkraut and lingonberry jam: the Christmas plate.', '1. Heat the oven to 200 °C.
2. Cut the potatoes into wedges, toss them with oil and salt and roast for 40 minutes.
3. Put the sausages on a buttered tray, prick them, and bake them for the last 20–25 minutes.
4. Warm the sauerkraut in a pan. Serve everything with lingonberry jam.', '🎄', 4, 50, ARRAY['800 g verivorst', '1 kg kartul', '500 g hapukapsas', 'pohlamoos']::text[], ARRAY['õli', 'või', 'sool']::text[], ARRAY['meat']::text[], ARRAY[11, 12, 1]::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-kapsarullid', 'Kapsarullid hakklihaga', 'Autumn cabbage leaves rolled around mince and rice, baked in sour cream.', '1. Boil the whole cabbage for 10 minutes and peel off 12 leaves. Cook the rice halfway.
2. Mix the mince, rice, chopped onion, salt and pepper.
3. Wrap a spoonful in each leaf and lay the rolls in an oiled dish.
4. Pour over the sour cream mixed with 200 ml water and bake at 180 °C for 45 minutes.', '🥬', 4, 90, ARRAY['1 kg kapsas', '500 g hakkliha', '100 g riis', '150 g sibul', '300 g hapukoor']::text[], ARRAY['õli', 'sool', 'pipar']::text[], ARRAY['meat']::text[], ARRAY[9, 10, 11]::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-kukeseenekaste-kartulitega', 'Kukeseenekaste kartulitega', 'Chanterelles in a cream sauce over potatoes: the taste of an Estonian August.', '1. Boil the potatoes.
2. Clean the chanterelles and fry them in butter with the chopped onion until their liquid is gone.
3. Pour in the cream, simmer for 5 minutes and season.
4. Serve over the potatoes with dill.', '🍄', 2, 30, ARRAY['400 g kukeseened', '150 g sibul', '200 ml vahukoor', '600 g kartul', 'till']::text[], ARRAY['või', 'sool', 'pipar']::text[], ARRAY['veggie']::text[], ARRAY[7, 8, 9]::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-noorkartul-suitsukalaga', 'Noorkartul suitsukala ja hapukoorega', 'New potatoes with hot-smoked fish, dill sour cream and cucumber. Summer on a plate.', '1. Scrub the new potatoes and boil them for 15 minutes.
2. Mix the sour cream with chopped dill and a pinch of salt.
3. Slice the cucumber.
4. Serve the potatoes with butter, the smoked fish and the dill cream.', '☀️', 2, 25, ARRAY['800 g kartul', '300 g kuumsuitsukala', '200 g hapukoor', '300 g kurk', 'till']::text[], ARRAY['või', 'sool']::text[], ARRAY['fish']::text[], ARRAY[6, 7, 8]::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-ahjulohe-sparglitega', 'Ahjulõhe sparglitega', 'Salmon and fresh asparagus roasted on one tray with lemon, with buttered potatoes. Spring in 25 minutes.', '1. Heat the oven to 200 °C and boil the potatoes.
2. Lay the salmon and the trimmed asparagus on a tray and drizzle with oil, salt and pepper.
3. Roast for 12–15 minutes.
4. Squeeze over the lemon and serve with buttered potatoes.', '🌱', 2, 25, ARRAY['400 g lõhefilee', '250 g spargel', '500 g kartul', '1 tk sidrun']::text[], ARRAY['oliiviõli', 'või', 'sool', 'pipar']::text[], ARRAY['fish']::text[], ARRAY[5, 6]::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-tacoohtu', 'Tacoõhtu', 'Everyone builds their own: spiced mince, tortillas, salsa, vegetables, cheese and sour cream.', '1. Fry the mince, add the taco spice mix and a little water, and simmer for 5 minutes.
2. Chop the tomatoes, cucumber and lettuce into bowls.
3. Warm the tortillas in the oven or a dry pan.
4. Put everything on the table and let people fill their own.', '🌮', 6, 30, ARRAY['800 g hakkliha', '2 tortilla', 'taco maitseainesegu', 'salsa kaste', '400 g tomatid', '300 g kurk', 'jääsalat', '200 g riivjuust', '300 g hapukoor']::text[], ARRAY['õli']::text[], ARRAY['meat', 'friends']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-lasanje', 'Lasanje', 'Layers of meat sauce, white sauce and pasta, baked until bubbling. Make it ahead when friends come.', '1. Fry the onion and mince, add the tomatoes, season and simmer for 15 minutes.
2. For the white sauce, melt 50 g butter, stir in 3 spoons of flour, then whisk in the milk until thick.
3. Layer meat sauce, pasta sheets and white sauce three times; finish with white sauce and the cheese.
4. Bake at 190 °C for 40 minutes and let it rest for 10.', '🍝', 6, 90, ARRAY['250 g lasanjeplaadid', '600 g hakkliha', '800 g purustatud tomatid', '150 g sibul', '750 ml piim', '200 g riivjuust']::text[], ARRAY['või', 'nisujahu', 'küüslauk', 'sool', 'pipar']::text[], ARRAY['pasta', 'meat', 'friends']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-ahjukana-juurviljadega', 'Ahjukana juurviljadega', 'A whole chicken roasted over potatoes, carrots and beetroot. One tray, little work, everyone fed.', '1. Heat the oven to 200 °C.
2. Cut the vegetables into chunks, toss them with oil, salt and garlic and spread them on a deep tray.
3. Rub the chicken with oil, salt and pepper, put the halved lemon inside and set it on the vegetables.
4. Roast for about 1 h 15 min, until the juices run clear. Rest for 10 minutes before carving.', '🍗', 6, 90, ARRAY['1,5 kg terve broiler', '1 kg kartul', '500 g porgand', '500 g peet', '150 g sibul', '1 tk sidrun']::text[], ARRAY['oliiviõli', 'küüslauk', 'sool', 'pipar']::text[], ARRAY['chicken', 'friends']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-seakaelapraad-ploomidega', 'Seakaelapraad ploomidega', 'Pork neck slow-roasted with prunes, potatoes and carrots: a Sunday dinner for guests.', '1. Heat the oven to 170 °C. Rub the pork with salt and pepper and brown it on all sides.
2. Put it in a roasting dish with the onion, prunes, a bay leaf and 300 ml water.
3. Cover and roast for 1 hour.
4. Add the potatoes and carrots in chunks, uncover and roast for 45 minutes more. Slice and serve with the juices.', '🥩', 6, 120, ARRAY['1,2 kg sea kaelakarbonaad', '200 g kuivatatud ploomid', '1 kg kartul', '500 g porgand', '150 g sibul']::text[], ARRAY['õli', 'loorberileht', 'sool', 'pipar']::text[], ARRAY['meat', 'friends']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-seenerisoto', 'Seenerisoto', 'Creamy mushroom risotto finished with butter and parmesan. Stir, talk, pour a glass.', '1. Dissolve a stock cube in 1.2 litres of hot water.
2. Fry the onion in butter, add the rice and stir for a minute.
3. Add the stock a ladle at a time, stirring, for about 18 minutes. Fry the sliced mushrooms separately and stir them in.
4. Take it off the heat, stir in a knob of butter and the grated parmesan, and season.', '🍚', 4, 40, ARRAY['300 g risotoriis', '400 g šampinjonid', '150 g sibul', '100 g parmesan']::text[], ARRAY['või', 'oliiviõli', 'puljongikuubik', 'sool', 'pipar']::text[], ARRAY['rice', 'veggie', 'friends']::text[], '{}'::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-saslokk', 'Šašlõkk ja värsked köögiviljad', 'Ready-marinated pork shashlik from the grill, with tomatoes, cucumber and rye bread. Midsummer (jaanipäev) on a plate.', '1. Light the grill and thread the shashlik onto skewers with onion rings.
2. Grill over glowing coals for 20–25 minutes, turning often.
3. Slice the tomatoes and cucumber.
4. Serve with rye bread and ketchup.', '🔥', 6, 45, ARRAY['1,5 kg šašlõkk', '500 g tomatid', '300 g kurk', '300 g sibul', 'rukkileib', 'ketšup']::text[], ARRAY['sool']::text[], ARRAY['meat', 'friends']::text[], ARRAY[5, 6, 7, 8]::int[], 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.')
ON CONFLICT (id) DO NOTHING;

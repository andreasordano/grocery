-- WEB-53: the sample dinners' lines checked product by product on 30 Oct; some picked the wrong thing
-- (coconut milk → a body lotion, beetroot → buttermilk, pumpkin → courgette, ginger → pickled sushi ginger,
-- tomatoes → tinned). New words that the stores match correctly. Only dinners nobody has edited yet
-- (updated = created): an edit in /admin.html is never overwritten.
UPDATE recipes SET ingredients = ARRAY['400 g kanafilee', '200 g basmati riis', '400 ml kookoskreem', '150 g sibul', '200 g paprika', 'karripasta']::text[], about = 'Chicken in a mild coconut curry with rice. A weeknight favourite that needs one pan.',
    method = '1. Cook the rice as the pack says.
2. Fry the chopped onion in oil, add the curry paste and fry for a minute.
3. Add the chicken in strips and the sliced pepper, and fry for 5 minutes.
4. Pour in the coconut milk and simmer for 10 minutes. Season and serve with the rice.', notes = 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'
WHERE id = 'pr-kanakarri-riisiga' AND updated = created;
UPDATE recipes SET ingredients = ARRAY['1 kg muskaatkõrvits', '300 g porgand', '150 g sibul', 'ingverijuur', '200 ml vahukoor', 'kõrvitsaseemned']::text[], about = 'A smooth autumn pumpkin soup with ginger and cream, topped with pumpkin seeds.',
    method = '1. Peel the pumpkin and carrots and cut them into cubes.
2. Soften the chopped onion and grated ginger in oil.
3. Add the vegetables, a stock cube and water to cover, and simmer for 20 minutes.
4. Blend until smooth, stir in the cream and season. Serve with toasted pumpkin seeds.', notes = 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'
WHERE id = 'pr-korvitsasupp' AND updated = created;
UPDATE recipes SET ingredients = ARRAY['400 g poolitatud herned', '600 g suitsuribi', '400 g kartul', '200 g porgand', '150 g sibul']::text[], about = 'Thick pea soup with smoked pork, eaten on Shrove Tuesday (vastlapäev) before going sledging.',
    method = '1. Soak the peas overnight, then rinse them.
2. Cover the peas and the smoked ribs with 2.5 litres of water and simmer for about an hour, skimming.
3. Lift out the ribs, cut off the meat and put it back.
4. Add the diced potatoes, carrot and onion and cook for 20 minutes more. Season.', notes = 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish. Barbora picks smoked chicken legs for ''suitsuribi''; Rimi has the smoked ribs.'
WHERE id = 'pr-hernesupp-suitsulihaga' AND updated = created;
UPDATE recipes SET ingredients = ARRAY['400 g külmutatud kukeseened', '150 g sibul', '200 ml vahukoor', '600 g kartul', 'till']::text[], about = 'Chanterelles in a cream sauce over potatoes: the taste of an Estonian August.',
    method = '1. Boil the potatoes.
2. Fry the chanterelles (fresh in season, else frozen) in butter with the chopped onion until their liquid is gone.
3. Pour in the cream, simmer for 5 minutes and season.
4. Serve over the potatoes with dill.', notes = 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'
WHERE id = 'pr-kukeseenekaste-kartulitega' AND updated = created;
UPDATE recipes SET ingredients = ARRAY['800 g hakkliha', '2 tortilla', 'taco maitseainesegu', 'salsa kaste', '400 g tomat', '300 g kurk', 'jääsalat', '200 g riivjuust', '300 g hapukoor']::text[], about = 'Everyone builds their own: spiced mince, tortillas, salsa, vegetables, cheese and sour cream.',
    method = '1. Fry the mince, add the taco spice mix and a little water, and simmer for 5 minutes.
2. Chop the tomatoes, cucumber and lettuce into bowls.
3. Warm the tortillas in the oven or a dry pan.
4. Put everything on the table and let people fill their own.', notes = 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'
WHERE id = 'pr-tacoohtu' AND updated = created;
UPDATE recipes SET ingredients = ARRAY['1,5 kg broileri koivad', '1 kg kartul', '600 g porgand', '300 g sibul', '1 tk sidrun']::text[], about = 'Chicken legs roasted over potatoes, carrots and onion. One tray, little work, everyone fed.',
    method = '1. Heat the oven to 200 °C.
2. Cut the vegetables into chunks, toss them with oil, salt and garlic and spread them on a deep tray.
3. Rub the chicken legs with oil, salt and pepper and lay them on the vegetables with the lemon in wedges.
4. Roast for about 50 minutes, until the skin is crisp and the juices run clear.', notes = 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'
WHERE id = 'pr-ahjukana-juurviljadega' AND updated = created;
UPDATE recipes SET ingredients = ARRAY['1,5 kg šašlõkk', '500 g tomat', '300 g kurk', '300 g sibul', 'rukkileib', 'ketšup']::text[], about = 'Ready-marinated pork shashlik from the grill, with tomatoes, cucumber and rye bread. Midsummer (jaanipäev) on a plate.',
    method = '1. Light the grill and thread the shashlik onto skewers with onion rings.
2. Grill over glowing coals for 20–25 minutes, turning often.
3. Slice the tomatoes and cucumber.
4. Serve with rye bread and ketchup.', notes = 'Drafted with AI (Claude) on 29 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'
WHERE id = 'pr-saslokk' AND updated = created;

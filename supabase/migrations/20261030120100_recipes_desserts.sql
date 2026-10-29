-- Desserts: 9 sample desserts for the recipes table, drafted with AI (Claude, 30 Oct 2026) for Estonian
-- tastes, under the Desserts chip only (data/dinner_chips.yaml, `apart`). Drafts: read them in /admin.html before
-- publishing. Every line was checked product by product at Rimi and Barbora on 30 Oct. ON CONFLICT DO NOTHING.
INSERT INTO recipes (id, name, about, method, emoji, servings, minutes, ingredients, pantry, tags, months, notes) VALUES
('pr-kamakreem-mustikatega', 'Kamakreem mustikatega', 'Kama, Estonia''s roasted grain flour, folded into whipped cream and quark, with blueberries. No cooking.', '1. Whip the cream with a spoon or two of sugar until soft peaks form.
2. Stir 4–5 spoons of kama into the quark, then fold in the whipped cream.
3. Layer the cream with the blueberries in glasses. Serve straight away or chill for an hour.', '🫐', 4, 10, ARRAY['kamajahu', '250 ml vahukoor', '200 g kohupiim', '400 g külmutatud mustikad']::text[], ARRAY['suhkur']::text[], ARRAY['dessert']::text[], '{}'::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-mannavaht-johvikatega', 'Mannavaht jõhvikatega', 'Pink, fluffy semolina whipped with cranberries, served with cold milk. A taste of every Estonian childhood.', '1. Simmer the cranberries in 800 ml water for 5 minutes, then strain the juice and bring it back to the boil with 100 g sugar.
2. Whisk in 100 g semolina and cook on low heat for 10 minutes, stirring.
3. Cool the pot in cold water, then whisk with a mixer for 5–10 minutes until pale pink and fluffy.
4. Serve with cold milk.', '🍓', 4, 30, ARRAY['300 g külmutatud jõhvikad', 'manna', '500 ml piim']::text[], ARRAY['suhkur']::text[], ARRAY['dessert']::text[], '{}'::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-kohupiimavorm-rosinatega', 'Kohupiimavorm rosinatega', 'A baked quark pudding with raisins and a sour cream top. Warm or cold, with jam.', '1. Heat the oven to 180 °C and butter a baking dish.
2. Mix the quark, eggs, 3 spoons of semolina, 100 g sugar and a handful of raisins.
3. Spread it in the dish and cover with the sour cream mixed with a spoon of sugar.
4. Bake for 35–40 minutes, until set and golden at the edges.', '🍮', 6, 50, ARRAY['500 g kohupiim', '3 tk munad', 'manna', 'rosinad', '200 g hapukoor']::text[], ARRAY['suhkur', 'või']::text[], ARRAY['dessert']::text[], '{}'::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-leivasupp-vahukoorega', 'Leivasupp vahukoorega', 'Sweet rye bread soup with raisins and apple, topped with whipped cream. Old-fashioned and loved.', '1. Tear the bread into pieces, cover with 1 litre of hot water and leave for 20 minutes.
2. Blend or mash it, then bring to the boil with the raisins, the chopped apples, 3 spoons of sugar and a pinch of cinnamon.
3. Simmer for 10 minutes, stirring; add water if it''s too thick.
4. Serve warm or cold with whipped cream.', '🍞', 4, 40, ARRAY['300 g rukkileib', 'rosinad', '2 tk õun', '200 ml vahukoor']::text[], ARRAY['suhkur', 'kaneel']::text[], ARRAY['dessert']::text[], '{}'::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-ounakook-kaneeliga', 'Õunakook kaneeliga', 'A simple sponge full of garden apples and cinnamon. Every Estonian kitchen in September.', '1. Heat the oven to 180 °C and butter a cake tin.
2. Beat the eggs with 150 g sugar until pale, then stir in the sour cream, 200 g flour and 2 teaspoons of baking powder.
3. Spread the batter in the tin and press in the sliced apples. Sprinkle with sugar and cinnamon.
4. Bake for 40 minutes, until a skewer comes out clean.', '🍎', 8, 60, ARRAY['800 g õunad', '3 tk munad', '200 g hapukoor']::text[], ARRAY['nisujahu', 'suhkur', 'või', 'küpsetuspulber', 'kaneel']::text[], ARRAY['dessert']::text[], ARRAY[8, 9, 10]::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-maasikad-vahukoorega', 'Maasikad vahukoorega', 'Estonian strawberries with whipped cream: the whole of July in one bowl.', '1. Rinse and hull the strawberries; halve the big ones.
2. Whip the cream with a little sugar and vanilla sugar.
3. Serve the strawberries with a big spoon of cream.', '🍓', 4, 10, ARRAY['600 g maasikad', '250 ml vahukoor']::text[], ARRAY['suhkur', 'vanillisuhkur']::text[], ARRAY['dessert']::text[], ARRAY[6, 7]::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-mustikapirukas', 'Mustikapirukas', 'Blueberry pie on puff pastry with a quark and sour cream filling. For a summer evening with friends.', '1. Heat the oven to 200 °C and line a tin with the rolled-out puff pastry.
2. Mix the quark, sour cream, eggs and 100 g sugar and spread it over the pastry.
3. Toss the blueberries with a spoon of potato starch and a little sugar and scatter them on top.
4. Bake for 30 minutes and let it cool a little.', '🥧', 8, 45, ARRAY['lehttaigen', '400 g külmutatud mustikad', '250 g kohupiim', '200 g hapukoor', '2 tk munad']::text[], ARRAY['suhkur', 'kartulijahu']::text[], ARRAY['dessert', 'friends']::text[], ARRAY[7, 8]::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.'),
('pr-piparkoogid', 'Piparkoogid', 'Gingerbread biscuits from ready dough, cut and decorated together: the smell of an Estonian December.', '1. Heat the oven to 200 °C. Roll the dough out thin on a floured table.
2. Cut shapes and lay them on a tray with baking paper.
3. Bake for 5–7 minutes, until just darker at the edges.
4. Let them cool, then decorate with icing sugar mixed with a few drops of water.', '🎄', 8, 40, ARRAY['1 kg piparkoogitainas']::text[], ARRAY['nisujahu', 'tuhksuhkur']::text[], ARRAY['dessert', 'friends']::text[], ARRAY[11, 12]::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish. Check that Barbora''s ''Piparkook KALEV 1kg'' is dough, not baked biscuits; Rimi had no dough on 30 Oct.'),
('pr-brita-kook', 'Brita kook', 'The Estonian celebration cake: sponge and meringue with almonds, filled with whipped cream and strawberries.', '1. Heat the oven to 175 °C. Beat 125 g butter with 100 g sugar, then the 4 yolks, 4 spoons of milk, 125 g flour and 1 teaspoon of baking powder. Spread in two lined tins.
2. Whisk the 4 egg whites stiff with 200 g sugar, spread the meringue over both cakes and scatter the almonds on one.
3. Bake for 25–30 minutes and let them cool completely.
4. Whip the cream, fold in the thawed strawberries, and put it between the layers, almond side up.', '🎂', 10, 60, ARRAY['4 tk munad', '400 ml vahukoor', '400 g külmutatud maasikad', 'mandlilaastud']::text[], ARRAY['nisujahu', 'suhkur', 'või', 'küpsetuspulber', 'piim']::text[], ARRAY['dessert', 'friends']::text[], '{}'::int[], 'Drafted with AI (Claude) on 30 Oct 2026 for Estonian home cooking. Read the amounts and method, cook it if you can, then publish.')
ON CONFLICT (id) DO NOTHING;

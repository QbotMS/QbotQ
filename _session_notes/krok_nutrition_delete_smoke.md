# Nutrition delete/correct smoke

- create kiwi: `OK` - wpis `kiwi testowe`, meal_id `108`, 42 kcal, dzienny bilans 252 kcal
- delete kiwi: `OK` - meal_id `108` usunięty, dzienny bilans spadł do 210 kcal
- create mango: `OK` - wpis `mango testowe`, meal_id `109`, 90 kcal, dzienny bilans 300 kcal
- correct mango: `OK` - meal_id `109` poprawiony na 95 kcal, dzienny bilans 305 kcal
- delete mango: `OK` - meal_id `109` usunięty, dzienny bilans spadł do 210 kcal
- create gruszka regression: `OK` - wpis `gruszka testowa`, meal_id `110`, 60 kcal, dzienny bilans 270 kcal
- delete gruszka regression: `OK` - meal_id `110` usunięty, dzienny bilans spadł do 210 kcal
- final DB state: tylko prawdziwy wpis użytkownika `Drugie śniadanie` (id `107`), bilans dnia `210 kcal`

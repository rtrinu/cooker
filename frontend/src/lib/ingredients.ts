/**
 * Ingredient names in the source data are mostly free-text recipe lines with
 * no USDA category, so the browser infers a kitchen-friendly group from the
 * name and falls back to the explicit category when there is one.
 */

const DB_LABELS: Record<string, string> = {
  'Alcoholic Beverage': 'Drinks',
  'American Indian/Alaska Native Foods': 'Indigenous foods',
  'Baby Foods': 'Pantry',
  'Baked Products': 'Baking & sweets',
  'Beef Products': 'Meat',
  Beverages: 'Drinks',
  'Breakfast Cereals': 'Grains & pasta',
  'Cereal Grains and Pasta': 'Grains & pasta',
  'Dairy and Egg Products': 'Dairy & eggs',
  'Ethnic Foods': 'Pantry',
  'Fast Foods': 'Pantry',
  'Fats and Oils': 'Oils & condiments',
  'Finfish and Shellfish Products': 'Seafood',
  'Fruits and Fruit Juices': 'Fruit',
  'Lamb, Veal, and Game Products': 'Meat',
  'Legumes and Legume Products': 'Legumes & nuts',
  'Meals, Entrees, and Side Dishes': 'Pantry',
  'Nut and Seed Products': 'Legumes & nuts',
  'Pork Products': 'Meat',
  'Poultry Products': 'Meat',
  'Restaurant Foods': 'Pantry',
  'Sausages and Luncheon Meats': 'Meat',
  Snacks: 'Pantry',
  'Soups, Sauces, and Gravies': 'Oils & condiments',
  'Spices and Herbs': 'Spices & herbs',
  Sweets: 'Baking & sweets',
  'Vegetables and Vegetable Products': 'Vegetables',
}

type Rule = { label: string; match: RegExp }

// Order matters: the first match wins, so specific foods come before generic
// words (peanut butter before butter, chicken stock before chicken).
const RULES: Rule[] = [
  {
    label: 'Drinks',
    match:
      /\b(wine|beer|ale|lager|stout|cider|sake|vodka|rum|whisk(e)?y|brandy|cognac|gin|liqueur|schnapps|coffee|espresso|tea|juice|lemonade|soda|cola|water|champagne|sherry|vermouth|bourbon|scotch|tequila|mead)(?:s|es)?\b/,
  },
  {
    label: 'Oils & condiments',
    match:
      /\b(oil|vinegar|sauce|ketchup|catsup|mustard|mayo(nnaise)?|dressing|stock|broth|bouillon|gravy|salsa|tahini|tamari|miso|paste|syrup|jam|jelly|jelley|preserve|marmalade|relish|chutney|sriracha|worcestershire|soy|hoisin|pesto|aioli|hummus|peanut butter|almond butter|nut butter|coconut milk)(?:s|es)?\b/,
  },
  {
    label: 'Vegetables',
    match:
      /\b(onion|shallot|scallion|garlic|tomato|potato|carrot|celery|mushroom|courgette|zucchini|cucumber|lettuce|cabbage|broccoli|cauliflower|sprout|spinach|kale|chard|arugula|rocket|watercress|leek|beet|beetroot|radish|turnip|parsnip|swede|rutabaga|squash|pumpkin|corn|sweetcorn|asparagus|artichoke|eggplant|aubergine|okra|fennel|bell pepper|sweet pepper|chilli|chili|jalapeno|jalapeño|poblano|serrano|olive|caper|gherkin|pickle|pea|peas|green bean|snow pea|snap pea)(?:s|es)?\b/,
  },
  {
    label: 'Fruit',
    match:
      /\b(apple|banana|lemon|lime|orange|grapefruit|berry|berries|strawberry|blueberry|raspberry|blackberry|currant|cranberry|grape|peach|pear|plum|cherry|mango|pineapple|melon|watermelon|cantaloupe|apricot|fig|date|raisin|sultana|prune|avocado|coconut|kiwi|papaya|guava|pomegranate|rhubarb|plantain|tangerine|clementine|mandarin|passion fruit|lychee)(?:s|es)?\b/,
  },
  {
    label: 'Spices & herbs',
    match:
      /\b(salt|pepper|peppercorn|cumin|paprika|cinnamon|oregano|basil|thyme|rosemary|parsley|cilantro|coriander|turmeric|curry|nutmeg|clove|bay leaf|bay leaves|dill|mint|sage|cardamom|saffron|allspice|anise|fennel seed|mustard seed|celery seed|sumac|za'atar|zaatar|chive|tarragon|marjoram|lemongrass|galangal|horseradish|wasabi|spice|herb|seasoning|masala|garam)(?:s|es)?\b/,
  },
  {
    label: 'Baking & sweets',
    match:
      /\b(flour|sugar|vanilla|chocolate|cocoa|baking powder|baking soda|bicarbonate|yeast|starch|cornstarch|cornflour|honey|molasses|treacle|icing|frosting|candy|marshmallow|caramel|toffee|sprinkle|food colouring|food coloring|gelatin|gelatine)(?:s|es)?\b/,
  },
  {
    label: 'Grains & pasta',
    match:
      /\b(rice|pasta|noodle|spaghetti|macaroni|penne|linguine|lasagne|lasagna|bread|baguette|roll|bun|oat|oats|quinoa|barley|couscous|bulgur|tortilla|wrap|cereal|cracker|breadcrumb|semolina|wheat|rye|polenta|cornmeal|millet|buckwheat|vermicelli|panko)(?:s|es)?\b/,
  },
  {
    label: 'Legumes & nuts',
    match:
      /\b(bean|beans|lentil|chickpea|garbanzo|soybean|edamame|tofu|tempeh|seitan|nut|nuts|almond|walnut|pecan|peanut|cashew|pistachio|hazelnut|macadamia|brazil nut|sesame|sunflower|pumpkin seed|chia|flax|hemp seed|pine nut)(?:s|es)?\b/,
  },
  {
    label: 'Dairy & eggs',
    match:
      /\b(milk|cream|creme|cheese|yogurt|yoghurt|butter|buttermilk|curd|egg|eggs|yolk|yolks|mozzarella|cheddar|parmesan|feta|ricotta|mascarpone|ghee|kefir)(?:s|es)?\b/,
  },
  {
    label: 'Meat',
    match:
      /\b(chicken|beef|pork|lamb|mutton|veal|turkey|duck|goose|rabbit|venison|bacon|ham|sausage|chorizo|salami|pepperoni|prosciutto|pancetta|steak|mince|ground|brisket|ribs|thigh|breast|wing|liver|kidney|oxtail|meatball)(?:s|es)?\b/,
  },
  {
    label: 'Seafood',
    match:
      /\b(fish|salmon|tuna|cod|haddock|tilapia|trout|mackerel|sardine|anchovy|anchovies|shrimp|prawn|crab|lobster|oyster|clam|mussel|scallop|squid|calamari|octopus|seafood|shellfish|anglerfish|halibut|bass|pollock|hake|snapper|eel)(?:s|es)?\b/,
  },
]

const GROUP_ORDER = [
  'Vegetables',
  'Fruit',
  'Dairy & eggs',
  'Meat',
  'Seafood',
  'Grains & pasta',
  'Legumes & nuts',
  'Spices & herbs',
  'Oils & condiments',
  'Baking & sweets',
  'Drinks',
  'Pantry',
]

export function ingredientGroup(name: string, category = '') {
  const lower = name.toLowerCase()
  // Foods containing a generic word that belongs to another group.
  if (/\bbaking soda\b|\bbicarbonate of soda\b|\bcream of tartar\b/.test(lower)) {
    return 'Baking & sweets'
  }
  if (/\bwater chestnut/.test(lower)) {
    return 'Vegetables'
  }
  for (const rule of RULES) {
    if (rule.match.test(lower)) {
      return rule.label
    }
  }
  return DB_LABELS[category] ?? 'Pantry'
}

export function groupRank(label: string) {
  const index = GROUP_ORDER.indexOf(label)
  return index === -1 ? GROUP_ORDER.length : index
}

// Everyday staples first, so the first screen of the browser is useful rather
// than a list of whatever names happen to be shortest.
const COMMON = [
  'salt',
  'pepper',
  'oil',
  'olive oil',
  'flour',
  'sugar',
  'eggs',
  'milk',
  'butter',
  'water',
  'onions',
  'garlic',
  'tomatoes',
  'potatoes',
  'carrots',
  'rice',
  'pasta',
  'bread',
  'cheese',
  'chicken',
  'beef',
  'pork',
  'lemon',
  'lime',
  'ginger',
  'thyme',
  'paprika',
  'cumin',
  'cinnamon',
  'vanilla',
  'honey',
  'oats',
  'yogurt',
  'cream',
  'baking powder',
  'baking soda',
  'black pepper',
  'vinegar',
  'soy sauce',
  'chocolate',
  'cocoa',
]

const COMMON_RANK = new Map(COMMON.map((name, index) => [name, index]))

function baseName(name: string) {
  return name
    .toLowerCase()
    .replace(/\([^)]*\)/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function commonRank(name: string) {
  const base = baseName(name)
  const exact = COMMON_RANK.get(base)
  if (exact !== undefined) {
    return exact
  }
  const first = base.match(/[a-z]+/)?.[0] ?? ''
  const firstRank = COMMON_RANK.get(first)
  if (firstRank !== undefined) {
    return COMMON.length + firstRank
  }
  return COMMON.length * 2
}

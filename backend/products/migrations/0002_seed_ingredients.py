from django.db import migrations


HARAM = "haram"
DOUBTFUL = "doubtful"

# ~40 hand-curated entries sourced from IFANCA/JAKIM published ingredient guides.
# Aliases are used by the classifier for case-insensitive substring matching
# against the raw ingredient text from Open Food Facts.
SEED_INGREDIENTS = [
    # -------------------------------------------------------------------------
    # HARAM
    # -------------------------------------------------------------------------
    {
        "name": "Lard",
        "e_number": "",
        "aliases": ["pork fat", "pork lard", "saindoux", "manteca", "porcine fat"],
        "category": HARAM,
        "reason": "Pork fat directly derived from pig — forbidden in Islam.",
    },
    {
        "name": "Pork",
        "e_number": "",
        "aliases": ["swine", "pig", "porcine", "sus scrofa"],
        "category": HARAM,
        "reason": "Pork in any form is explicitly forbidden (haram) in Islam.",
    },
    {
        "name": "Pork Gelatin",
        "e_number": "",
        "aliases": ["gelatin (pork)", "pork-derived gelatin", "gelatine (pork)"],
        "category": HARAM,
        "reason": "Gelatin derived from pig bones or skin — haram regardless of processing method.",
    },
    {
        "name": "Pork Fat",
        "e_number": "",
        "aliases": ["animal fat (pork)", "pork adipose", "pork grease"],
        "category": HARAM,
        "reason": "Fat derived from pork — forbidden.",
    },
    {
        "name": "Pork Enzymes",
        "e_number": "",
        "aliases": ["porcine enzymes", "pork-derived enzymes"],
        "category": HARAM,
        "reason": "Enzymes derived from pork — forbidden.",
    },
    {
        "name": "Bacon",
        "e_number": "",
        "aliases": ["bacon bits", "smoked bacon", "pork bacon", "bacon flavor (pork)"],
        "category": HARAM,
        "reason": "Cured pork product — forbidden.",
    },
    {
        "name": "Ham",
        "e_number": "",
        "aliases": ["prosciutto", "serrano ham", "jambon", "speck", "pork ham"],
        "category": HARAM,
        "reason": "Cured or cooked pork leg — forbidden.",
    },
    {
        "name": "Blood",
        "e_number": "",
        "aliases": ["animal blood", "blood meal", "dried blood", "blood powder"],
        "category": HARAM,
        "reason": "Blood as a food ingredient is explicitly forbidden in Islam.",
    },
    {
        "name": "Blood Plasma",
        "e_number": "",
        "aliases": ["plasma protein", "blood plasma protein", "animal plasma"],
        "category": HARAM,
        "reason": "Derived from animal blood — forbidden.",
    },
    {
        "name": "Ethanol",
        "e_number": "",
        "aliases": [
            "ethyl alcohol",
            "grain alcohol",
            "alcohol (ethyl)",
            "drinking alcohol",
            "potable alcohol",
        ],
        "category": HARAM,
        "reason": (
            "Ethyl alcohol as a deliberate food ingredient is forbidden. "
            "Applies to intentional use — not to trace fermentation byproducts such as in vinegar."
        ),
    },
    {
        "name": "Wine",
        "e_number": "",
        "aliases": ["white wine", "red wine", "cooking wine", "wine extract", "vin"],
        "category": HARAM,
        "reason": "Alcoholic beverage derived from grapes — forbidden as an ingredient.",
    },
    {
        "name": "Beer",
        "e_number": "",
        "aliases": ["ale", "stout", "lager", "malt beverage", "barley wine"],
        "category": HARAM,
        "reason": "Fermented alcoholic beverage — forbidden as an ingredient.",
    },
    {
        "name": "Liquor",
        "e_number": "",
        "aliases": [
            "spirits",
            "whiskey",
            "whisky",
            "vodka",
            "brandy",
            "cognac",
            "bourbon",
            "gin",
            "rum",
            "tequila",
            "sake",
            "absinthe",
            "schnapps",
        ],
        "category": HARAM,
        "reason": "Distilled alcoholic spirit — forbidden as an ingredient.",
    },
    # -------------------------------------------------------------------------
    # DOUBTFUL
    # -------------------------------------------------------------------------
    {
        "name": "Gelatin",
        "e_number": "",
        "aliases": ["gelatine", "hydrolyzed collagen", "collagen (gelatin)"],
        "category": DOUBTFUL,
        "reason": (
            "May be derived from pork, beef, or fish — source is almost never stated on labels. "
            "Pork gelatin is haram; beef gelatin is halal only if from a properly slaughtered animal; "
            "fish gelatin is generally permissible. When source is unlabeled, treat as Doubtful."
        ),
    },
    {
        "name": "Mono- and Diglycerides",
        "e_number": "E471",
        "aliases": [
            "monoglycerides",
            "diglycerides",
            "mono and diglycerides",
            "mono- & diglycerides",
            "monoglycerides of fatty acids",
            "diglycerides of fatty acids",
            "glycerol monostearate",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Emulsifiers that can be derived from plant oils or animal fats (including pork). "
            "Source is not required on labels. When labeled simply as 'mono- and diglycerides' "
            "without specifying plant origin, treat as Doubtful."
        ),
    },
    {
        "name": "L-Cysteine",
        "e_number": "E920",
        "aliases": ["cysteine", "l-cysteine hydrochloride", "cysteine hydrochloride"],
        "category": DOUBTFUL,
        "reason": (
            "Amino acid used as a dough conditioner — commonly sourced from duck/chicken feathers "
            "or human hair, though synthetic versions exist. Source is rarely disclosed. "
            "Treat as Doubtful unless synthetic origin is confirmed."
        ),
    },
    {
        "name": "Natural Flavors",
        "e_number": "",
        "aliases": [
            "natural flavor",
            "natural flavoring",
            "natural flavorings",
            "natural flavour",
            "natural flavours",
            "artificial and natural flavors",
        ],
        "category": DOUBTFUL,
        "reason": (
            "An umbrella term that can include alcohol-based flavor carriers, animal-derived "
            "flavor compounds (castoreum, civet), or plant-based sources. "
            "The actual composition is a trade secret and rarely disclosed."
        ),
    },
    {
        "name": "Vanilla Extract",
        "e_number": "",
        "aliases": ["pure vanilla extract", "vanilla extract (alcohol)", "vanilla flavoring"],
        "category": DOUBTFUL,
        "reason": (
            "Pure vanilla extract is typically ~35% ethanol by regulation in the US. "
            "Imitation vanilla and vanilla flavor may or may not contain alcohol — "
            "source and alcohol content are rarely specified on ingredient lists."
        ),
    },
    {
        "name": "Enzymes",
        "e_number": "",
        "aliases": [
            "enzyme",
            "microbial enzymes",
            "fungal enzymes",
            "protease",
            "amylase",
            "cellulase",
            "xylanase",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Enzymes may be derived from microbial (permissible), plant, or animal sources. "
            "When listed generically without source specification, treat as Doubtful."
        ),
    },
    {
        "name": "Rennet",
        "e_number": "",
        "aliases": [
            "animal rennet",
            "calf rennet",
            "chymosin",
            "rennet (animal)",
            "coagulating enzyme",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Enzyme used to curdle milk for cheese. Animal rennet (from calf stomach) requires "
            "halal slaughter to be permissible; microbial/FPC rennet is generally halal. "
            "Source is often unlabeled — treat as Doubtful."
        ),
    },
    {
        "name": "Carmine",
        "e_number": "E120",
        "aliases": [
            "carminic acid",
            "crimson lake",
            "natural red 4",
            "c.i. 75470",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Red colorant extracted from cochineal insects (Dactylopius coccus). "
            "Scholarly disagreement exists: some jurists permit it under istihalah "
            "(transformation), others prohibit insect-derived ingredients outright. "
            "Flagged as Doubtful pending the user's madhab preference."
        ),
    },
    {
        "name": "Cochineal",
        "e_number": "E120",
        "aliases": ["cochineal extract", "cochineal color", "carmine lake"],
        "category": DOUBTFUL,
        "reason": (
            "Same source as Carmine — insect-derived red colorant. "
            "Scholarly disagreement on permissibility — see Carmine."
        ),
    },
    {
        "name": "Whey",
        "e_number": "",
        "aliases": [
            "whey powder",
            "whey protein",
            "whey protein concentrate",
            "whey protein isolate",
            "dried whey",
            "sweet whey",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Byproduct of cheese-making. Permissibility depends on the rennet used to produce "
            "the original cheese — animal rennet requires halal slaughter. "
            "Source is almost never traceable from the label alone."
        ),
    },
    {
        "name": "Shellac",
        "e_number": "E904",
        "aliases": [
            "confectioner's glaze",
            "confectionery glaze",
            "resinous glaze",
            "pharmaceutical glaze",
            "lac",
            "lac resin",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Resin secreted by the lac insect (Kerria lacca), used as a glazing agent on candies "
            "and pills. Scholarly disagreement on insect-derived ingredients — treat as Doubtful."
        ),
    },
    {
        "name": "Isinglass",
        "e_number": "",
        "aliases": ["fish gelatin (isinglass)", "fish fining agent"],
        "category": DOUBTFUL,
        "reason": (
            "Fining agent derived from dried fish swim bladders, used to clarify beer and wine. "
            "Generally permissible as fish-derived, but its use in alcoholic beverages makes "
            "the final product haram — context-dependent, flagged Doubtful."
        ),
    },
    {
        "name": "Glycerin",
        "e_number": "E422",
        "aliases": [
            "glycerol",
            "glycerine",
            "vegetable glycerin",
            "vegetable glycerol",
            "glycerol (e422)",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Can be derived from plant oils (permissible) or animal fats (requires halal source). "
            "When labeled simply as 'glycerin' without specifying plant origin, treat as Doubtful."
        ),
    },
    {
        "name": "Stearic Acid",
        "e_number": "E570",
        "aliases": [
            "octadecanoic acid",
            "stearate",
            "calcium stearate",
            "magnesium stearate",
            "sodium stearate",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Fatty acid that can be derived from animal fat (including pork) or plant oils. "
            "Source is not disclosed on food labels — treat as Doubtful."
        ),
    },
    {
        "name": "Lipase",
        "e_number": "",
        "aliases": ["animal lipase", "porcine lipase", "lipase enzyme"],
        "category": DOUBTFUL,
        "reason": (
            "Fat-digesting enzyme used in cheese and bakery products. "
            "May be animal-derived (including porcine) or microbial. "
            "Source is rarely specified — treat as Doubtful."
        ),
    },
    {
        "name": "Pepsin",
        "e_number": "",
        "aliases": ["porcine pepsin", "pepsin enzyme"],
        "category": DOUBTFUL,
        "reason": (
            "Digestive enzyme typically extracted from pig stomachs. "
            "Some scholars permit it under istihalah (complete transformation), "
            "others prohibit porcine-derived enzymes entirely — flagged Doubtful."
        ),
    },
    {
        "name": "Lecithin",
        "e_number": "E322",
        "aliases": [
            "soy lecithin",
            "sunflower lecithin",
            "egg lecithin",
            "lecithin (soy)",
            "lecithin (sunflower)",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Usually soy-derived (halal) but can also come from egg yolk or animal sources. "
            "When labeled without origin (just 'lecithin'), source is unknown — treat as Doubtful. "
            "'Soy lecithin' and 'sunflower lecithin' are generally considered halal."
        ),
    },
    {
        "name": "Polysorbate 80",
        "e_number": "E433",
        "aliases": [
            "polyoxyethylene sorbitan monooleate",
            "polysorbate",
            "polysorbate 20",
            "polysorbate 60",
            "tween 80",
        ],
        "category": DOUBTFUL,
        "reason": (
            "Emulsifier that may be derived from animal fats (oleic acid from tallow) "
            "or plant sources. The oleic acid component's origin is not typically disclosed."
        ),
    },
    {
        "name": "Natural Beef Flavor",
        "e_number": "",
        "aliases": ["beef flavoring", "beef extract", "beef tallow flavoring"],
        "category": DOUBTFUL,
        "reason": (
            "May be derived from beef not slaughtered according to halal requirements, "
            "or may contain other non-halal flavor compounds. "
            "Halal status depends on the slaughter method of the source animal."
        ),
    },
    {
        "name": "Castoreum",
        "e_number": "",
        "aliases": ["beaver extract", "castoreum extract"],
        "category": DOUBTFUL,
        "reason": (
            "Secretion from beaver scent glands used as a natural flavor — "
            "may be listed under 'natural flavors'. Scholarly disagreement on permissibility; "
            "most consider it impermissible as it is derived from an animal not slaughtered "
            "according to halal requirements."
        ),
    },
    {
        "name": "Emulsifier",
        "e_number": "",
        "aliases": ["emulsifiers", "emulsifying agent", "emulsifying agents"],
        "category": DOUBTFUL,
        "reason": (
            "Generic label that could refer to any of several emulsifiers, "
            "some animal-derived (e.g. E471 mono- and diglycerides) and some plant-derived. "
            "Treat as Doubtful when no specific emulsifier is identified."
        ),
    },
]


def seed_ingredients(apps, schema_editor):
    Ingredient = apps.get_model("products", "Ingredient")
    Ingredient.objects.bulk_create([Ingredient(**entry) for entry in SEED_INGREDIENTS])


def remove_seed_ingredients(apps, schema_editor):
    Ingredient = apps.get_model("products", "Ingredient")
    names = [entry["name"] for entry in SEED_INGREDIENTS]
    Ingredient.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_ingredients, reverse_code=remove_seed_ingredients),
    ]

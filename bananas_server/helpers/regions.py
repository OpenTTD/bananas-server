import json
import os
import unicodedata

REGIONS = {}

folder = os.getcwd()
if not os.path.exists(f"{folder}/region-un-m49.csv"):
    folder = os.environ["PYTHONPATH"]
if not os.path.exists(f"{folder}/region-un-m49.csv"):
    raise Exception("Unable to locate region files. Please run from the root of the project.")

with open(f"{folder}/region-un-m49.csv") as fp:
    # Skip the CSV header.
    next(fp)

    for line in fp.readlines():
        line = line.strip().split(";")

        if len(line) != 15:
            raise Exception("Invalid line; is the UN M49 CSV file corrupted?")

        (
            global_code,
            global_name,
            region_code,
            region_name,
            sub_region_code,
            sub_region_name,
            intermediate_region_code,
            intermediate_region_name,
            country,
            _,
            country_code,
            _,
            _,
            _,
            _,
        ) = line

        if global_code != "001":
            raise Exception("Invalid global code; is this an UN M49 CSV file from earth?")

        if not country_code:
            continue

        # If the intermediate region is set, ignore the sub region.
        # This is because in these cases the sub region tends to be a long
        # name and doesn't add information to the (intermediate) region.
        if intermediate_region_code:
            sub_region_code = intermediate_region_code
            sub_region_name = intermediate_region_name

        # Prefix UN specific codes with UN-. This to give them a visual
        # difference from the ISO codes.
        if region_code:
            region_code = f"UN-{region_code}"
        if sub_region_code:
            sub_region_code = f"UN-{sub_region_code}"

        REGIONS[country_code] = {
            "name": country,
            "parent": sub_region_code,
        }
        if sub_region_code:
            REGIONS[sub_region_code] = {
                "name": sub_region_name,
                "parent": region_code,
            }
        if region_code:
            REGIONS[region_code] = {
                "name": region_name,
                "parent": None,
            }
        if global_code:
            REGIONS[global_code] = {
                "name": global_name,
                "parent": None,
            }


with open(f"{folder}/region-iso-3166-1.json") as fp:
    data = json.load(fp)

    for country in data["3166-1"]:
        country_code = country["alpha_2"]
        country_name = country.get("common_name", country["name"]).split(",")[0].strip()

        # Debian has a much better friendly name for many countries.
        # So use that name instead of the official one the UN is using.
        # Example:
        # Official name: United Kingdom of Great Britain and Northern Ireland
        # Debian's name: United Kingdom
        if country_code in REGIONS:
            REGIONS[country_code]["name"] = country_name
        elif country_code == "TW":
            # Taiwan is not in the UN dataset, but is in the 3166-1 dataset.
            REGIONS[country_code] = {
                "name": country_name,
                "parent": "UN-030",  # Eastern Asia
            }


with open(f"{folder}/region-iso-3166-2.json") as fp:
    data = json.load(fp)

    for country in data["3166-2"]:
        subdivision_code = country["code"]
        # Normalize all names to be within ASCII. This makes searching in-game easier.
        subdivision_name = unicodedata.normalize("NFKD", country["name"]).encode("ascii", "ignore").decode()

        # There are several ways to denote aliases; strip those out.
        subdivision_name = subdivision_name.lstrip("/")
        subdivision_name = subdivision_name.split("/")[0].strip()
        subdivision_name = subdivision_name.split("(")[0].strip()
        subdivision_name = subdivision_name.split("[")[0].strip()
        subdivision_name = subdivision_name.split(",")[0].strip()

        country_code = subdivision_code[:2]

        REGIONS[subdivision_code] = {
            "name": subdivision_name,
            "parent": country_code,
        }

REGIONS["UN-MARS"] = {
    "name": "Mars",
    "parent": None,
}

# According to wikipedia (https://en.wikipedia.org/wiki/ISO_3166-2:GB) these
# are part of ISO 3166-2, but the ISO doesn't mention them. So we insert them.
REGIONS["GB-ENG"] = {
    "name": "England",
    "parent": "GB",
}
REGIONS["GB-NIR"] = {
    "name": "Northern Ireland",
    "parent": "GB",
}
REGIONS["GB-SCT"] = {
    "name": "Scotland",
    "parent": "GB",
}
REGIONS["GB-WLS"] = {
    "name": "Wales",
    "parent": "GB",
}

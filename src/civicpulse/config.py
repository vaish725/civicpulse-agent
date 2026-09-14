"""Static configuration for the demo: one city, one neighborhood profile.

No user auth or multi-city support in this version (see project scope) -
a single hardcoded profile is enough to demonstrate genuine relevance and
urgency judgment against a real agenda feed.
"""

import os

from dotenv import load_dotenv

# Loads a local .env file into the environment if one exists (never
# committed, see .gitignore); lets ANTHROPIC_API_KEY and MODEL_PROVIDER be
# set once in a file instead of exported in every shell that runs this.
load_dotenv()

# Legistar client identifier and the body we watch. San Jose publishes many
# bodies (council, committees, boards); we scope the demo to City Council
# general business and consent items so the pull stays a manageable size.
CITY_ID = "sanjose"
LEGISTAR_BASE_URL = f"https://webapi.legistar.com/v1/{CITY_ID}"
COUNCIL_BODY_ID = 138  # "City Council" in the sanjose Legistar bodies list

# Bedrock model used for every reasoning tool (relevance, urgency, summary,
# drafting). One model is enough for the MVP; region must match wherever
# Claude model access was enabled in the AWS account. Bedrock requires an
# inference profile ID (the "us." prefix) rather than the bare model ID for
# on-demand invocation of current-generation Claude models.
#
# Claude Sonnet 5 is not yet enabled on this account's Bedrock model access
# list (it is the newest release and rolls out separately from older
# models); Sonnet 4.5 is confirmed working and is used here until Sonnet 5
# access is requested in the Bedrock console.
BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
BEDROCK_REGION = "us-east-1"

# Bedrock is the default, AWS-native path. MODEL_PROVIDER=anthropic switches
# to calling the same model directly via the Anthropic API instead, using
# ANTHROPIC_API_KEY from the environment; this exists because Bedrock model
# invocation can be blocked by AWS-account-level issues entirely unrelated
# to this code (see README, "A sudden, account-wide Error 002"), and having
# a second, independent path means that kind of outage does not block
# testing or demoing the agent's actual reasoning. Same underlying model
# snapshot as BEDROCK_MODEL_ID, so behavior should be effectively the same,
# though the two are not guaranteed byte-identical.
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "bedrock")
ANTHROPIC_MODEL_ID = "claude-sonnet-4-5-20250929"

# Neighborhood group priorities. Each one is a plain-language description,
# not a keyword list, because assess_relevance is a semantic reasoning call:
# an item should be able to match a priority even when it shares no words
# with it (e.g. a zoning variance matching "affordable housing").
#
# Kept to four, deliberately sharp and non-overlapping. One is a decoy with
# no expected match in the current agenda pull, included on purpose to prove
# the agent can correctly say "not relevant" instead of padding results.
NEIGHBORHOOD_PRIORITIES = [
    {
        "name": "housing_affordability",
        "description": (
            "New affordable housing supply, subsidies, incentives, or fee "
            "waivers for residential development; policies that increase or "
            "decrease the cost or availability of housing."
        ),
    },
    {
        "name": "housing_accessibility",
        "description": (
            "Disability access and fair housing compliance in land use and "
            "zoning, such as reasonable accommodation requests or ADA-related "
            "design standard modifications. Distinct from general housing "
            "affordability or supply policy."
        ),
    },
    {
        "name": "downtown_parking_and_small_business",
        "description": (
            "Parking availability, pricing, or hours in commercial and "
            "downtown areas, and their effect on small businesses and "
            "neighborhood commercial vitality."
        ),
    },
    {
        "name": "school_funding_and_youth_programs",
        "description": (
            "School district budgets, funding, or youth program decisions. "
            "Included as a standing priority even though it will not match "
            "every agenda cycle."
        ),
    },
]

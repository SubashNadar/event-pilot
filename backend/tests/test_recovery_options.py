"""A recovery offer leaves out what the owner has already applied, so the next choice is a new one."""

from app.agents.recovery import fresh_options
from app.models.run import RecoveryOption


def option(id_, patch, action="retry_with"):
    return RecoveryOption(id=id_, label=id_, description=id_, action=action, patch=patch)


def test_option_already_in_effect_is_not_offered_again():
    options = [option("search-hebbal", {"location": "Hebbal"}), option("unverified", {"allow_unverified": True})]
    kept = fresh_options(options, {"location": "Hebbal"})
    assert [o.id for o in kept] == ["retry", "unverified"]


def test_a_plain_retry_is_always_available_when_everything_else_was_applied():
    kept = fresh_options([option("search-hebbal", {"location": "Hebbal"})], {"location": "Hebbal"})
    assert [o.action for o in kept] == ["retry"]


def test_a_different_value_for_the_same_key_is_still_a_new_choice():
    kept = fresh_options([option("search-whitefield", {"location": "Whitefield"})], {"location": "Hebbal"})
    assert [o.id for o in kept] == ["retry", "search-whitefield"]

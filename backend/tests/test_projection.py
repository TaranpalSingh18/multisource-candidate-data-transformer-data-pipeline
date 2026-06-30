from app.projection import ProjectionConfig, project_profile
from app.schemas import CandidateProfile, Skill
from uuid import uuid4


def _sample_profile() -> CandidateProfile:
  return CandidateProfile(
      id=uuid4(),
      full_name="Alice Doe",
      headline="Senior Engineer",
      primary_email="alice@example.com",
      emails=["alice@example.com", "alice+alt@example.com"],
      phones=["+14155552671"],
      location="San Francisco",
      country="US",
      years_experience=7.5,
      skills=[Skill(name="Python", confidence=0.9), Skill(name="React", confidence=0.8)],
      experience=[],
      education=[],
      overall_confidence=0.9,
  )


def test_projection_happy_path_with_from_and_array_index():
  profile = _sample_profile()
  config = ProjectionConfig.model_validate(
      {
          "fields": [
              {"path": "name", "from": "full_name", "type": "string", "required": True},
              {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
              {"path": "skills", "from": "skills[].name", "type": "string[]"},
          ],
          "include_provenance": False,
          "include_confidence": True,
          "on_missing": "null",
      }
  )

  out = project_profile(profile, config)
  assert out["name"] == "Alice Doe"
  assert out["primary_email"] == "alice@example.com"
  assert out["skills"] == ["Python", "React"]


def test_projection_on_missing_null_and_omit():
  profile = _sample_profile()
  config_null = ProjectionConfig.model_validate(
      {
          "fields": [{"path": "full_name_copy", "from": "full_name", "type": "string"}],
          "on_missing": "null",
      }
  )
  out_null = project_profile(profile, config_null)
  assert "full_name_copy" in out_null and out_null["full_name_copy"] == "Alice Doe"

  config_omit = ProjectionConfig.model_validate(
      {
          "fields": [{"path": "nonexistent", "from": "location[99]", "type": "string"}],
          "on_missing": "omit",
      }
  )
  out_omit = project_profile(profile, config_omit)
  assert "nonexistent" not in out_omit


def test_projection_on_missing_error_raises():
  profile = _sample_profile()
  config = ProjectionConfig.model_validate(
      {
          "fields": [{"path": "nonexistent", "type": "string", "required": True}],
          "on_missing": "error",
      }
  )
  try:
      project_profile(profile, config)
      assert False, "Expected ValueError for missing required field"
  except ValueError:
      pass


def test_invalid_root_field_in_config_is_rejected():
  profile = _sample_profile()
  config = ProjectionConfig.model_validate(
      {
          "fields": [{"path": "x", "from": "does_not_exist", "type": "string"}],
      }
  )
  try:
      project_profile(profile, config)
      assert False, "Expected ValueError for invalid root field"
  except ValueError:
      pass


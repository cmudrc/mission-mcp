"""OVS — Output Verification System checks for Mission MCP CPACS output.

Validates that the Mission adapter writes expected XPaths with plausible values.
Self-contained: no cross-repo dependencies.
"""

from xml.etree import ElementTree as ET

SAMPLE_MISSION_OUTPUT = """\
<?xml version="1.0"?>
<cpacs>
  <vehicles>
    <aircraft>
      <model uID="test">
        <name>OVS Test Aircraft</name>
        <analysisResults>
          <mission>
            <backend>aviary</backend>
            <converged>true</converged>
            <fuel_burned_kg>5812.3</fuel_burned_kg>
            <gtow_kg>62732.4</gtow_kg>
            <wing_mass_kg>6421.2</wing_mass_kg>
            <reserve_fuel_kg>581.2</reserve_fuel_kg>
            <trajectory_points>50</trajectory_points>
            <range_nmi>1500.0</range_nmi>
            <segments>
              <segment><type>climb</type></segment>
              <segment><type>cruise</type></segment>
              <segment><type>descent</type></segment>
            </segments>
          </mission>
        </analysisResults>
      </model>
    </aircraft>
  </vehicles>
</cpacs>
"""


def test_mission_output_structure():
    root = ET.fromstring(SAMPLE_MISSION_OUTPUT)
    assert root.tag == "cpacs"
    assert root.find(".//vehicles/aircraft") is not None


def test_mission_results_present():
    root = ET.fromstring(SAMPLE_MISSION_OUTPUT)
    mission = root.find(".//analysisResults/mission")
    assert mission is not None


def test_mission_backend():
    root = ET.fromstring(SAMPLE_MISSION_OUTPUT)
    be = root.find(".//analysisResults/mission/backend")
    assert be is not None and be.text in ("aviary", "nseg")


def test_mission_converged():
    root = ET.fromstring(SAMPLE_MISSION_OUTPUT)
    conv = root.find(".//analysisResults/mission/converged")
    assert conv is not None and conv.text in ("true", "false")


def test_mission_fuel_burned_range():
    root = ET.fromstring(SAMPLE_MISSION_OUTPUT)
    el = root.find(".//analysisResults/mission/fuel_burned_kg")
    assert el is not None and el.text is not None
    val = float(el.text)
    assert 0.0 <= val <= 500000.0


def test_mission_gtow_range():
    root = ET.fromstring(SAMPLE_MISSION_OUTPUT)
    el = root.find(".//analysisResults/mission/gtow_kg")
    assert el is not None and el.text is not None
    val = float(el.text)
    assert 0.0 <= val <= 1e7


def test_mission_segments():
    root = ET.fromstring(SAMPLE_MISSION_OUTPUT)
    segs = root.find(".//analysisResults/mission/segments")
    assert segs is not None
    assert len(segs) > 0


def test_mission_range():
    root = ET.fromstring(SAMPLE_MISSION_OUTPUT)
    el = root.find(".//analysisResults/mission/range_nmi")
    assert el is not None and el.text is not None
    val = float(el.text)
    assert 0.0 <= val <= 20000.0

from ues_bot.scrape import assignment_is_submitted, enrich_from_event_page, find_assignment_url, parse_events_from_dashboard


DASHBOARD_HTML = """
<div class="event" data-region="event-item">
  <h6><a data-action="view-event" data-event-id="42" href="http://x.com?event=42">Tarea 1</a></h6>
  <div class="date small"><a>2026-03-01</a></div>
</div>
<div class="event" data-region="event-item">
  <h6><a data-action="view-event" data-event-id="43" href="http://x.com?event=43">Tarea 2</a></h6>
  <div class="date small"><a>2026-03-05</a></div>
</div>
"""


def test_parse_events_from_dashboard():
    events = parse_events_from_dashboard(DASHBOARD_HTML)
    assert len(events) == 2
    assert events[0].event_id == "42"
    assert events[0].title == "Tarea 1"
    assert events[1].event_id == "43"


def test_parse_events_from_empty_dashboard():
    events = parse_events_from_dashboard("<html><body></body></html>")
    assert events == []


def test_assignment_is_submitted_detected():
    html = '<table class="generaltable"><tr><th>Submission status</th><td class="submissionstatussubmitted">Submitted for grading</td></tr></table>'
    submitted, _status = assignment_is_submitted(html)
    assert submitted is True


def test_assignment_is_submitted_not_submitted():
    html = '<table class="generaltable"><tr><th>Submission status</th><td class="submissionstatusnosubmission">No submission</td></tr></table>'
    submitted, _status = assignment_is_submitted(html)
    assert submitted is False


def test_assignment_is_submitted_unknown():
    html = "<html><body>Nothing here</body></html>"
    submitted, status = assignment_is_submitted(html)
    assert submitted is None
    assert status == "No detectado"


def test_find_assignment_url():
    html = '<a href="https://ueslearning.ues.mx/mod/assign/view.php?id=100">Ver</a>'
    url = find_assignment_url(html, base="https://ueslearning.ues.mx")
    assert url == "https://ueslearning.ues.mx/mod/assign/view.php?id=100"


def test_find_assignment_url_not_found():
    html = '<a href="https://other.com/page">Link</a>'
    url = find_assignment_url(html, base="https://ueslearning.ues.mx")
    assert url == ""


def test_enrich_from_event_page():
    html = """
    <a href="/course/view.php?id=5">Calculo II</a>
    <div class="description-content">Entregar ejercicios del capitulo 3.</div>
    """
    course, desc = enrich_from_event_page(html)
    assert course == "Calculo II"
    assert "capitulo 3" in desc

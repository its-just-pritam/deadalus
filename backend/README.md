# Crew Operations Backend

Backend for the AI-assisted airline crew control decision-support system described in [problem-guide.md](../problem-guide.md).

## Status

Initial modular-monolith structure created. A Docker Compose importer now loads the repository's JSON data into a persistent SQLite database volume.

## Architecture

The backend keeps operational authority in deterministic domain services. The LLM is responsible for natural-language understanding, tool selection, and explanation of verified results. It must not calculate aviation legality or invent crew assignments.

```text
API / Conversational Controller
        |
Application Services
        |
Domain Services and Rules Engine
        |
Repositories / SQLite
```

## Directory Structure

```text
backend/
  api/                         HTTP and conversational endpoints
  application/                 Use-case orchestration
  domain/
    crew/                      Crew profiles and availability
    flights/                   Flight schedules and aircraft
    pairings/                  Crew pairing relationships
    reserves/                  Reserve pool operations
    rules/                     Duty, rest, qualification, and base rules
    recommendations/           Candidate evaluation and ranking
  infrastructure/
    database/                  SQLite setup and migrations
    repositories/              Data access implementations
  llm/                         LLM adapter and verified-result explanations
  tests/                       Unit and integration tests
```

## Planned Core Services

- `ImpactAnalyzer`: identifies pairings and flights affected by crew absence.
- `RulesEngine`: applies the seven operational rules deterministically.
- `CandidateEvaluator`: validates reserve candidates and records violations.
- `CostCalculator`: estimates replacement, deadhead, and delay costs.
- `RecommendationEngine`: ranks legal candidates by cost, coverage, and impact.
- `AuditService`: records facts, rules checked, calculations, and decisions.

## Key Workflow

```text
Crew absence
  -> Impact analysis
  -> Pairing expansion
  -> Affected flights
  -> Reserve search
  -> Candidate evaluation
  -> Rules validation
  -> Cost and coverage calculation
  -> Ranked recommendations
  -> LLM explanation
```

## Data Sources

The SQLite database is initialized from the JSON files in the repository's `data/` directory. Scalar fields become typed columns. Nested objects and arrays become child tables with a `parent_id` foreign key and an `id` primary key. For example, `crew.ratings` is imported into `crew_ratings`, and `pairings.days` is imported into `rosters_pairings_days`. The `questions.expected_answer` value is intentionally kept as serialized JSON in one column because it is reference content rather than operational data that needs relational queries.

Natural identifier fields such as `crew_id`, `flight_id`, and `pairing_id` are retained as unique columns. Where the target table is known, these fields also receive foreign keys. Apart from the intentional `questions.expected_answer` exception, no source JSON is stored in a database cell.

## Database Import

SQLite is an embedded database and does not run as a network server. The Compose service is therefore a one-shot importer that writes the database to the persistent `sqlite_data` volume.

From the repository root, run:

```bash
docker compose up sqlite-web
```

This imports the JSON files and starts the SQLite web server at [http://localhost:8080](http://localhost:8080). The generated database is stored inside the Docker volume at `/var/lib/sqlite/crew_operations.db`.

To import updated JSON files, rerun the importer before starting the web service:

```bash
docker compose run --rm sqlite-import
docker compose up sqlite-web
```

The importer replaces the imported tables on each run, making the command repeatable when the JSON data changes. SQLite remains an embedded database; `sqlite-web` provides browser-based access rather than a database wire-protocol server.

## Development Notes

- Prefer a modular monolith for this prototype.
- Keep legality calculations deterministic, auditable, and testable.
- Treat unknown or missing operational data as unresolved, not legal.
- Keep `docker-compose.yml` and the JSON importer updated when database setup changes.
- Update this README when backend structure, services, APIs, data schema, or setup instructions change.

## Data Model

The database-independent entities live in `domain/entities.py`. They cover the
operational tables in `crew_operations.db`: `Crew`, `Flight`, `Pairing`,
`Reserve`, `Certification`, `DutyClock`, `RiskSignal`, `CostConfig`, `Rule`
and `Scenario`. Nested JSON data is represented as immutable tuples on the
parent entity.

SQLite implementations are in
`infrastructure/repositories/repositories.py`. Each repository accepts a
`sqlite3.Connection`, returns entities rather than database rows, and hides the
generated `parent_id` relationships. Use the connection factory to ensure
row-oriented access and foreign-key enforcement:

```python
from backend.infrastructure.database.connection import connect
from backend.infrastructure.repositories import CrewRepository

connection = connect("crew_operations.db")
crew = CrewRepository(connection).get("C-1042")
```

Question prompts and scenario answer keys are reference/judging data and are
intentionally not part of this operational model layer.

The first implemented retrieval API is the Q01 reserve lookup. Install the
dependencies from `requirements.txt` and start FastAPI with:

```bash
pip install -r backend/requirements.txt
uvicorn backend.api.main:app --reload
```

The SQLite path defaults to `crew_operations.db` at the repository root. The
API exposes:

- `GET /api/reserves?date=2026-09-15&base=BLR` - reserves active on the date,
  including each reserve's on-call window.
- `GET /api/reserves/{crewId}/on-call-window` - one reserve's window.
- `GET /api/crew/{crewId}` - crew profile, rank, and ratings.
- `GET /api/crew/{crewId}/duty-clock` - 7-day duty and 28-day flight snapshot.
- `GET /api/crew/{crewId}/duty-history` - daily duty and flight-hour history.
- `GET /api/duty-clocks/{crewId}/headroom?asOf=` - RULE-DUTY-02 headroom.
- `GET /api/rules/{ruleId}` - rule text and parameters.

The LangChain agent is available through:

- `POST /api/chat` - accepts `{"question": "..."}` and returns an LLM answer.
- `GET /api/chat/history?session_id=default` - returns the persisted chat messages
  for a session. Chat messages are stored in the `chat_history` table, which is
  created by the SQLite importer during Docker database boot and preserved when
  operational tables are re-imported.

The agent has retrieval tools backed by the HTTP API, including
`get_duty_clock`, `get_duty_history`, `get_duty_headroom`, and `get_rule` for
Q02. Its system instructions
require tool retrieval for operational facts rather than allowing the model to
answer those facts from memory.

Reserve-window interpretation: the window constrains when a reserve may be
called, not the scheduled report time. Reachability determines whether a call
made within the window can support the report. A report after the window ends
is not, by itself, an on-call violation.

Each retrieval call logs the tool name, HTTP path, query parameters, status, and
duration. Response bodies and API keys are not logged. View these logs with:

```bash
docker compose logs -f backend
```

Configure the required `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` values.
Reasoning is enabled with OpenRouter's `extra_body` request option. The
integration always uses `https://openrouter.ai/api/v1`. You may also configure
`OPENROUTER_SITE_URL` and `OPENROUTER_SITE_NAME` for attribution. Install the
dependencies from `requirements.txt`.

Example:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"Which BLR reserves are available on 2026-09-15?"}'
```

To run the API in Docker, start the importer and API service:

```bash
docker compose up --build backend
```

The API is available at `http://localhost:8000`, with interactive
documentation at `http://localhost:8000/docs`. The container reads the
database from the shared `sqlite_data` volume and uses
`CREW_OPERATIONS_DB=/var/lib/sqlite/crew_operations.db`.

Routes are organized into resource-specific controller classes under
`api/controllers/`: `CrewController` owns crew routes and `ReserveController`
owns reserve and on-call-window routes. `api/main.py` only creates the FastAPI
application and includes their routers.

### Physical Table Aggregation Map

The importer creates 51 physical tables. Repositories aggregate them into the
following API-facing entities:

| Physical table | Aggregated entity / property |
|---|---|
| `crew` | `Crew` |
| `crew_ratings` | `Crew.ratings` |
| `certifications` | `Certification` |
| `flights` | `Flight` |
| `rosters` | `Roster` |
| `rosters_pairings` | `Roster.pairings` (`Pairing`) |
| `rosters_pairings_crew` | `Pairing.crew` (`PairingCrew`) |
| `rosters_pairings_days` | `Pairing.days` (`PairingDay`) |
| `rosters_pairings_days_flights` | `PairingDay.flight_ids` |
| `rosters_flagged_exceptions` | `Roster.flagged_exceptions` |
| `reserve_pool` | `Reserve` |
| `reserve_pool_dates` | `Reserve.dates` |
| `reserve_pool_oncall_window_utc` | `Reserve.oncall_window_utc` |
| `duty_clocks` | `DutyClock` |
| `duty_clocks_daily_history` | `DutyClock.daily_history` (`DutyHistory`) |
| `risk_signals` | `RiskSignal` |
| `risk_signals_drivers` | `RiskSignal.drivers` |
| `costs` | `CostConfig` |
| `rules` | `Ruleset` |
| `rules_definitions` | `Ruleset.definitions` |
| `rules_rules` | `Ruleset.rules` (`Rule`) |
| `rules_rules_params` | `Rule.parameters` (`RuleParameters`) |
| `questions` | `Question` |
| `questions_rules_ref` | `Question.rules_ref` |
| `scenarios` | `Scenario` |
| `scenarios_event` | `Scenario.event` (`ScenarioEvent`) |
| `scenarios_event_events` | `Scenario.event.events` |
| `scenarios_event_window_utc` | `Scenario.event.window_utc` |
| `scenarios_answer_key` | `Scenario.answer_key` (`ScenarioAnswerKey`) |
| `scenarios_answer_key_affected_flights` | `ScenarioAnswerKey.affected_flights` |
| `scenarios_answer_key_uncovered_flights` | `ScenarioAnswerKey.uncovered_flights` |
| `scenarios_answer_key_uncovered_flights_day1` | `ScenarioAnswerKey.uncovered_flights_day1` |
| `scenarios_answer_key_uncovered_flights_day2` | `ScenarioAnswerKey.uncovered_flights_day2` |
| `scenarios_answer_key_options` | `ScenarioAnswerKey.options` (`ScenarioOption`) |
| `scenarios_answer_key_options_rules_checked` | `ScenarioOption.rules_checked` |
| `scenarios_answer_key_options_dxa` | Scenario answer-key DXA options |
| `scenarios_answer_key_options_dxa_rules_checked` | DXA option `rules_checked` |
| `scenarios_answer_key_options_dxb` | Scenario answer-key DXB options |
| `scenarios_answer_key_options_dxb_rules_checked` | DXB option `rules_checked` |
| `scenarios_answer_key_expected_choice` | `ScenarioAnswerKey.expected_choice` |
| `scenarios_answer_key_expected_choice_rules_checked` | Expected choice `rules_checked` |
| `scenarios_answer_key_excluded_candidates` | `ScenarioAnswerKey.excluded_candidates` |
| `scenarios_answer_key_excluded_dxa` | `ScenarioAnswerKey.excluded_dxa` |
| `scenarios_answer_key_excluded_dxb` | `ScenarioAnswerKey.excluded_dxb` |
| `scenarios_answer_key_illegal_assignment` | `ScenarioAnswerKey.illegal_assignment` |
| `scenarios_answer_key_per_flight_assessment` | `ScenarioAnswerKey.per_flight_assessment` |
| `scenarios_answer_key_optimal_joint_plan` | Joint-plan total cost |
| `scenarios_answer_key_optimal_joint_plan_assign_dxa` | Optimal joint-plan DXA assignment |
| `scenarios_answer_key_optimal_joint_plan_assign_dxa_rules_checked` | DXA assignment `rules_checked` |
| `scenarios_answer_key_optimal_joint_plan_assign_dxb` | Optimal joint-plan DXB assignment |
| `scenarios_answer_key_optimal_joint_plan_assign_dxb_rules_checked` | DXB assignment `rules_checked` |

## API Status

These endpoints are recommended to support the 38 questions in
`data/questions.json`. Entries marked <span style="color: green">[implemented]</span>
are registered in the current FastAPI application. Entries marked
<span style="color: goldenrod">[planned]</span> are design references
and are not available yet.

### Reference Data

- <span style="color: goldenrod">[planned]</span> `GET /api/questions`
- <span style="color: goldenrod">[planned]</span> `GET /api/questions/{questionId}`
- <span style="color: goldenrod">[planned]</span> `GET /api/rules`
- <span style="color: green">[implemented]</span> `GET /api/rules/{ruleId}`
- <span style="color: goldenrod">[planned]</span> `GET /api/costs`
- <span style="color: goldenrod">[planned]</span> `GET /api/scenarios`
- <span style="color: goldenrod">[planned]</span> `GET /api/scenarios/{scenarioId}`

### Crew

- <span style="color: goldenrod">[planned]</span> `GET /api/crew`
- <span style="color: green">[implemented]</span> `GET /api/crew/{crewId}`
- <span style="color: green">[implemented]</span> `GET /api/crew/{crewId}/ratings`
- <span style="color: goldenrod">[planned]</span> `GET /api/crew/{crewId}/certifications`
- <span style="color: green">[implemented]</span> `GET /api/crew/{crewId}/duty-clock`
- <span style="color: green">[implemented]</span> `GET /api/crew/{crewId}/duty-history`
- <span style="color: green">[implemented]</span> `GET /api/crew/{crewId}/risk-signal`
- <span style="color: goldenrod">[planned]</span> `GET /api/crew/{crewId}/pairings`
- <span style="color: green">[implemented]</span> `GET /api/crew/search?base=&rank=&status=&aircraftType=`

### Flights and Network

- <span style="color: green">[implemented]</span> `GET /api/flights?date=&departureStation=&arrivalStation=`
- <span style="color: green">[implemented]</span> `GET /api/flights/{flightId}`
- <span style="color: green">[implemented]</span> `GET /api/flights/departures?date=&station=`
- <span style="color: green">[implemented]</span> `GET /api/flights/routes?date=&departureStation=&arrivalStation=`
- <span style="color: green">[implemented]</span> `GET /api/flights/count?date=`
- <span style="color: green">[implemented]</span> `GET /api/flights/longest-block`
- <span style="color: goldenrod">[planned]</span> `GET /api/stations`
- <span style="color: green">[implemented]</span> `GET /api/stations/{station}/nonstop-destinations`
- <span style="color: goldenrod">[planned]</span> `GET /api/aircraft/{aircraft}/schedule`
- <span style="color: green">[implemented]</span> `GET /api/aircraft/{aircraft}/pairings`

### Rosters and Pairings

- <span style="color: goldenrod">[planned]</span> `GET /api/roster`
- <span style="color: goldenrod">[planned]</span> `GET /api/roster/exceptions`
- <span style="color: goldenrod">[planned]</span> `GET /api/pairings`
- <span style="color: green">[implemented]</span> `GET /api/pairings/{pairingId}`
- <span style="color: green">[implemented]</span> `GET /api/pairings/{pairingId}/crew`
- <span style="color: goldenrod">[planned]</span> `GET /api/pairings/{pairingId}/days`
- <span style="color: goldenrod">[planned]</span> `GET /api/pairings/{pairingId}/flights`
- <span style="color: goldenrod">[planned]</span> `GET /api/pairings?date=&aircraft=&crewId=`
- <span style="color: goldenrod">[planned]</span> `GET /api/pairings/{pairingId}/crew/{crewId}`

### Reserves

- <span style="color: green">[implemented]</span> `GET /api/reserves?date=&base=`
- <span style="color: green">[implemented]</span> `GET /api/reserves/{crewId}`
- <span style="color: goldenrod">[planned]</span> `GET /api/reserves?date=&base=&rank=&calloutTime=`
- <span style="color: goldenrod">[planned]</span> `GET /api/reserves/available?date=&base=&rank=&reportTime=`
- <span style="color: green">[implemented]</span> `GET /api/reserves/{crewId}/on-call-window`

### Operational Queries

- <span style="color: green">[implemented]</span> `GET /api/duty-clocks/{crewId}/headroom?asOf=`
- <span style="color: green">[implemented]</span> `GET /api/duty-clocks/at-risk?date=&minimumDutyHours=`
- <span style="color: green">[implemented]</span> `GET /api/certifications/expiring?from=&to=`
- <span style="color: goldenrod">[planned]</span> `GET /api/assignments/{pairingId}/crew-impact?crewId=&date=`
- <span style="color: goldenrod">[planned]</span> `GET /api/flights/{flightId}/passenger-impact`
- <span style="color: green">[implemented]</span> `GET /api/flights/affected?station=&from=&to=`
- <span style="color: green">[implemented]</span> `GET /api/flights/{flightId}/cancellation-impact`
- <span style="color: green">[implemented]</span> `GET /api/flights/most-seats`
- <span style="color: green">[implemented]</span> `GET /api/crew/{crewId}/qualification?aircraftType=&date=`
- <span style="color: green">[implemented]</span> `GET /api/crew/{crewId}/legality?pairingId=&date=`
- <span style="color: green">[implemented]</span> `GET /api/pairings/{pairingId}/legality?crewId=&date=&delayHours=`
- <span style="color: green">[implemented]</span> `GET /api/pairings/{pairingId}/rest-check?crewId=&date=`
- <span style="color: green">[implemented]</span> `GET /api/rest-check?releaseUtc=&crewId=`
- <span style="color: goldenrod">[planned]</span> `GET /api/pairings/{pairingId}/duty-check?crewId=&from=&to=`
- <span style="color: green">[implemented]</span> `GET /api/pairings/{pairingId}/fdp-check?crewId=&date=&delayHours=`
- <span style="color: green">[implemented]</span> `GET /api/reserves/available?date=&base=&rank=&reportTime=&aircraftType=`
- <span style="color: green">[implemented]</span> `GET /api/crew/{crewId}/downstream-rest-check?pairingId=&date=`

### Disruption and Recovery

- <span style="color: goldenrod">[planned]</span> `GET /api/disruptions/affected-flights?station=&from=&to=`
- <span style="color: goldenrod">[planned]</span> `GET /api/disruptions/affected-pairings?station=&from=&to=`
- <span style="color: goldenrod">[planned]</span> `GET /api/disruptions/uncrewed-flights?crewId=&pairingId=&date=`
- <span style="color: goldenrod">[planned]</span> `GET /api/recovery/candidates?pairingId=&crewRole=&date=`
- <span style="color: goldenrod">[planned]</span> `GET /api/recovery/options?pairingId=&crewId=&date=`
- <span style="color: goldenrod">[planned]</span> `GET /api/recovery/ranked-options?pairingId=&from=&to=`
- <span style="color: green">[implemented]</span> `GET /api/recovery/ranked-options?pairingId=&from=&to=`
- <span style="color: green">[implemented]</span> `GET /api/recovery/joint-plan?aircrafts=&date=`
- <span style="color: goldenrod">[planned]</span> `GET /api/recovery/briefing?date=`
- <span style="color: goldenrod">[planned]</span> `GET /api/aircraft/{aircraft}/morning-briefing?date=`

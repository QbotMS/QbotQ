# Data Routing Policy

This document defines which data belongs to which QBot module.
Before saving any structured information, QBot must classify it into a module.
If data does not clearly belong to Garage, Claude must not write it to Garage.
If the target module does not exist yet, Claude must report that and wait for a
QBot Task Spec that creates it.

## Core principle

Garage is not a general knowledge base.

## Garage — allowed data

Garage is only for:

- Bikes (brand, model, type, frame, purchase info)
- Components (groupset, wheels, tires, chain, cassette, brakes, saddle, etc.)
- Bike parts
- Bike accessories (lights, computer mounts, etc.)
- Purchases of bike parts and accessories
- Service records
- Wear tracking
- Mechanical bike setup (fitting, position)

Garage is implemented as `data/garage.db` (SQLite) with tables: bikes,
components, fitting, gear, memories, trips, packing_lists, packing_items.

## Garage — forbidden data

Garage must not store:

- Rider physiology (FTP, CP, W'bal, HRmax, body mass)
- Route planning (RWGPS, Komoot, GPX tracks, surface analysis)
- Activities (FIT files, replay logs, ride summaries)
- QEXT field configs
- Color palettes
- Advisor models
- Clothing notes (unless it is gear purchase/ownership record)
- Nutrition data
- Lab experiments
- General notes free-form (use `rider_profile` or `system`)

## Available data modules

| Module         | Purpose                                                      |
|---------------|--------------------------------------------------------------|
| garage        | Bike hardware, parts, service, wear tracking, mechanical setup |
| rider_profile | Rider physiology, FTP, CP, W'bal, HRmax, body mass, cadence preferences, fit profile |
| routes        | Planned routes, RWGPS, Komoot, QBot route copies, surface analysis |
| rides         | Completed activities, FIT exports, replay logs, ride summaries, post-ride notes |
| qext          | Karoo/QEXT field configs, palettes, advisor models, diagnostics, fixtures |
| lab           | Experiments, assumptions, model tests, validation reports |
| system        | Schemas, routing rules, audit logs, import queue, task specs |

## Routing decision flow

1. Classify the data using the module table above.
2. If data belongs to `garage` → write to `data/garage.db` using `db.py`.
3. If data belongs to any other module → check if that module's storage exists.
4. If the target module's storage does not exist yet → stop and report.
5. Do not write non-garage data to `data/garage.db` or `db.py` tables.

## Garage `memories` table — scope restriction

The `memories` table in Garage was historically used for general notes.
Under this policy, `memories` is restricted to:
- Fitting notes
- Bike/component service notes
- Wear tracking notes
- Bike-specific observations

General knowledge, rider physiology, route notes, and other non-garage data
must not be written to the `memories` table.

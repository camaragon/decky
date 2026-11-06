# 1. Version the pull request JSON interface

Status: accepted

## Context

Scripts need PR metadata without parsing terminal tables. The existing loader
already classifies review, team, and mine sources and applies shared filters.

## Decision

Expose opt-in JSON commands with an integer `version` envelope. Version 1 keeps
the loader's bucket names and snake_case fields, with explicit truncation notes.
Selection flags restrict buckets; JSON always disables the terminal picker.
The README defines field types and compatibility rules.

## Consequences

Consumers can reject unsupported versions and accept additive fields. Changes
to field meaning or shape require a version increment. GitHub limits and separate
API snapshots remain visible constraints rather than completeness guarantees.

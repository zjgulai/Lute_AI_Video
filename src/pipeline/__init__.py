"""Pipeline orchestrators package.

Importing ``src.pipeline`` must not register scenario or media skills. Scenario
modules own their required skill registrations, and S1 media skills are lazy
registered by step so no-media production smokes keep clean log windows.
"""

"""Publisher module for Cortex AI.

This module implements the Autonomous Publishing Module for the Cortex AI
project. It consumes an approved topic (from the Discovery layer) and a
persona (from the Brain layer), then autonomously generates, validates,
persists, and exposes LinkedIn-style technology publications through a
FastAPI backend.

Responsibility boundary: this module contains NO topic discovery, web
scraping, persona creation, memory, or opinion-engine logic. Those belong
to the Brain and Discovery layers. Everything here is limited to the
autonomous publishing workflow: fetch approved topic -> fetch persona ->
AI generation -> queue -> persist -> expose.
"""

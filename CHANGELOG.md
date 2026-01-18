# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2024-01-19

### Added

- **Core**: Initial release of the Orbit Backend Server.
- **API**: RESTful endpoints for Boards, Notes, Identities, and Upvotes.
- **Real-time**: Django Channels consumers for WebSocket broadcasting.
- **Tasks**: Celery + Redis setup for asynchronous housekeeping.
- **Auth**: Custom 'Ghost Identity' permission classes and JWT implementation.
- **Database**: PostgreSQL schema for rapid, optimized queries.

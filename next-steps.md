Next steps for implementation:

* Booking modal needs same calendar date picker icon as ground maintenance and external booking
* For Fixture Secretary - add a view of all bookings and their current status (pending, confirmed, rejected)
* For Team Managers - add a view of their bookings and their status
* General code refactor and tidy-up:
  * Make sure modals are all in separate files
  * Review look-and-feel across all screens and ensure consistency of buttons, inputs, tables, fonts, colours, etc
  * Review which screens/sections are modals vs forms on existing pages - e.g. team editing etc
  * Security review
  * Architectural review
* Venue to have "default" flag - when flag is set, this venue should be selected by default in the calendar view. Save method on venue model should ensure there is only one default venue, and should remove default flag from other venues if this one is set as default.
* Add pitch booking confirmation/rejection email notifications to fixture secretaries and team managers.
* Add play-cricket api integration to automatically pull fixtures. Only fixture secretary or admin can do this.

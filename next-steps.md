Next steps for implementation:

* Team management screen - improve for phone browser
  * Width of screen/horizontal scrolling
  * Edit and delete buttons not visible without hover - model on user management page
  * smooth scroll to edit section at the top
* Booking modal needs same calendar date picker icon as ground maintenance and external booking
* For Fixture Secretary - add a view of all bookings and their current status (pending, confirmed, rejected)
* For Team Managers - add a view of their bookings and their status
* General code refactor and tidy-up:
  * Make sure modals are all in separate files
  * Review look-and-feel across all screens and ensure consistency of buttons, inputs, tables, fonts, colours, etc
  * Security review
  * Architectural review
* Venue to have "default" flag - when flag is set, this venue should be selected by default in the calendar view. Save method on venue model should ensure there is only one default venue, and should remove default flag from other venues if this one is set as default.
* When an unapproved, pending request is already in place for a slot, this should be visible on the calendar view for all users, but should still allow managers to request the slot. It is up to the fixture secretary to decide which to approve.
* When multiple competing pending booking requests are present for the same slot, these should all be visible on the calendar view.
* When multiple competing pending booking requests are present for the same slot, this should be highlighted in the secretary panel. When the fixture secretary approves a request which overlaps with another, a confirmation modal should be shown for confirmation, and the other overlapping request(s) should be auto-rejected.
* Enhancements for mobile browser viewing -
  * slide-out hamburger menu for navigation instead of top navbar
  * reduce cell padding on calendar view
* Add pitch booking confirmation/rejection email notifications to fixture secretaries and team managers.
* Hosting options for the app need to be investigated and a decision made and the app deployed.
* Add play-cricket api integration to automatically pull fixtures. Only fixture secretary or admin can do this.
* Add spreadsheet/csv import of fixtures - only fixture secretary or admin can do this.

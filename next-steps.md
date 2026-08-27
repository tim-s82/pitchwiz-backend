Next steps for implementation:

* Add groundstaff role which has view access to fixtures, and can block pitches or whole venues for ground maintenance
* Need to add nets (lanes 1, 2 and 3) as bookable options, plus outfield only for training. These could either be listed as pitches, or perhaps could be marked as training facilities. If outfield is listed as a training facility, would need to ensure that it still blocks the main square and youth pitches.
* Bookings to be editable/cancellable by fixture secretaries (in progress)
* For Fixture Secretary - add a view of all bookings and their current status (pending, confirmed, rejected)
* For Team Managers - add a view of their bookings and their status
* Allow managers to cancel their own bookings (in progress)
* Allow managers to edit their own bookings (in progress)
* Pitch management screen to have a filter for venue
* Team management screen table to have column showing managers
* Landing page after login is always calendar view
* Venue to have "default" flag - when flag is set, this venue should be selected by default in the calendar view. Save method on venue model should ensure there is only one default venue, and should remove default flag from other venues if this one is set as default.
* Add Change Password button to nav bar to allow logged in user to change their password. Password dialog should have 3 fields - current password, new password, confirm new password. On submit the password should be validated (current password correct) and if valid, the new password should be set.
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

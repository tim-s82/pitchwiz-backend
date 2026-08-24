Next steps for implementation:

* Bug in calendar view - at one venue, there are three pitches. The main pitch blocks the two youth pitches, and each youth pitch in turn blocks the main pitch (but not each other). In the calendar view, youth pitch 1 correctly shows the main pitch as blocked, but the youth pitch 2 does not. The flag to indicate blocking of the pitch is correctly set in metadata but for some reason this is not being reflected in the calendar view. Need to thoroughly investigate and resolve.
* Venue/Pitch columns on the calendar view should be sorted consistently (alphabetically)
* Pitch booking request form to filter teams based on the selected pitch (i.e. compatible pitch lengths)
* Add groundstaff role which has view access to fixtures, and can block pitches or whole venues for ground maintenance
* Need to add nets (lanes 1, 2 and 3) as bookable options, plus outfield only for training. These could either be listed as pitches, or perhaps could be marked as training facilities. If outfield is listed as a training facility, would need to ensure that it still blocks the main square and youth pitches.
* Bookings to be editable/cancellable by fixture secretaries
* For Fixture Secretary - add a view of all bookings and their current status (pending, confirmed, rejected)
* For Team Managers - add a view of their bookings and their status
* Allow managers to cancel their own bookings
* Allow managers to edit their own bookings
* Pitch management screen to have a filter for venue
* Team management screen table to have column showing managers
* Landing page after login is always calendar view
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

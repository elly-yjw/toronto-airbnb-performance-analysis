# Data

Raw data is intentionally not committed to this repository.

Download the **Toronto, Ontario, Canada — 16 September 2026** files from
[Inside Airbnb](https://insideairbnb.com/get-the-data/) and place them in this folder:

- `listings.csv.gz` — Detailed Listings data
- `calendar.csv.gz` — Detailed Calendar data
- `reviews.csv.gz` — Detailed Review data

The analysis uses public Inside Airbnb data. Inside Airbnb states that its downloadable
data is licensed under the Creative Commons Attribution 4.0 International License.

## Important interpretation notes

- `estimated_occupancy_l365d` and `estimated_revenue_l365d` are modeled estimates,
  not verified host transactions.
- An unavailable calendar date can be booked **or** blocked by a host. This project
  therefore calls the calendar metric **unavailability**, not bookings or occupancy.
- Review activity is used as a proxy for guest activity/seasonality; not every stay
  produces a review.

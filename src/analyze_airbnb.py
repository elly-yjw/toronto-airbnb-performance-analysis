"""
Toronto Airbnb Market & Performance Benchmarking
=================================================

Expected raw files in data/:
- listings.csv.gz
- calendar.csv.gz
- reviews.csv.gz

Source: Inside Airbnb, Toronto snapshot dated 16 September 2026.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
IMAGES = ROOT / "images"

OUTPUTS.mkdir(exist_ok=True)
IMAGES.mkdir(exist_ok=True)


def load_and_clean_listings():
    df = pd.read_csv(DATA / "listings.csv.gz", low_memory=False)

    df["price_num"] = pd.to_numeric(
        df["price"]
        .astype("string")
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False),
        errors="coerce",
    )

    df = df[
        df["price_num"].notna()
        & df["estimated_revenue_l365d"].notna()
        & (df["price_num"] > 0)
    ].copy()

    return df


def aggregate_calendar(valid_ids):
    monthly_parts = []
    listing_parts = []

    for chunk in pd.read_csv(
        DATA / "calendar.csv.gz",
        usecols=["listing_id", "date", "available"],
        chunksize=500_000,
    ):
        chunk = chunk[chunk["listing_id"].isin(valid_ids)].copy()
        chunk["date"] = pd.to_datetime(chunk["date"])
        chunk["unavailable"] = (chunk["available"] == "f").astype("int8")
        chunk["month"] = chunk["date"].dt.to_period("M").astype(str)

        monthly_parts.append(
            chunk.groupby("month")
            .agg(
                calendar_days=("available", "size"),
                unavailable_days=("unavailable", "sum"),
            )
            .reset_index()
        )

        listing_parts.append(
            chunk.groupby("listing_id")
            .agg(
                calendar_days=("available", "size"),
                unavailable_days=("unavailable", "sum"),
            )
            .reset_index()
        )

    monthly = (
        pd.concat(monthly_parts)
        .groupby("month", as_index=False)[["calendar_days", "unavailable_days"]]
        .sum()
    )
    monthly["unavailability_rate"] = (
        monthly["unavailable_days"] / monthly["calendar_days"]
    )

    listing = (
        pd.concat(listing_parts)
        .groupby("listing_id", as_index=False)[["calendar_days", "unavailable_days"]]
        .sum()
    )
    listing["calendar_unavailability_rate"] = (
        listing["unavailable_days"] / listing["calendar_days"]
    )

    return monthly, listing


def analyze_reviews(valid_ids):
    reviews = pd.read_csv(
        DATA / "reviews.csv.gz",
        usecols=["listing_id", "date"],
        parse_dates=["date"],
    )
    reviews = reviews[reviews["listing_id"].isin(valid_ids)].copy()
    reviews["year"] = reviews["date"].dt.year
    reviews["month_num"] = reviews["date"].dt.month
    reviews["year_month"] = reviews["date"].dt.to_period("M").astype(str)

    monthly_reviews = (
        reviews.groupby("year_month")
        .size()
        .rename("reviews")
        .reset_index()
    )

    # Use complete recent years so a partial 2026 month does not distort seasonality.
    season = reviews[reviews["year"].isin([2024, 2025])].copy()
    counts = (
        season.groupby(["year", "month_num"])
        .size()
        .rename("reviews")
        .reset_index()
    )
    counts["year_total"] = counts.groupby("year")["reviews"].transform("sum")
    counts["monthly_share"] = counts["reviews"] / counts["year_total"]

    seasonality = (
        counts.groupby("month_num")
        .agg(
            avg_monthly_share=("monthly_share", "mean"),
            avg_reviews=("reviews", "mean"),
        )
        .reset_index()
    )

    return monthly_reviews, seasonality


def build_tables(df):
    room_summary = (
        df.groupby("room_type")
        .agg(
            listings=("id", "count"),
            median_price=("price_num", "median"),
            median_estimated_revenue=("estimated_revenue_l365d", "median"),
            mean_estimated_revenue=("estimated_revenue_l365d", "mean"),
            median_estimated_occupancy=("estimated_occupancy_l365d", "median"),
            median_reviews_ltm=("number_of_reviews_ltm", "median"),
        )
        .sort_values("listings", ascending=False)
        .reset_index()
    )

    one_bed = df[
        (df["room_type"] == "Entire home/apt")
        & (df["bedrooms"] == 1)
    ].copy()

    neighbourhood = (
        one_bed.groupby("neighbourhood_cleansed")
        .agg(
            listings=("id", "count"),
            median_price=("price_num", "median"),
            median_estimated_revenue=("estimated_revenue_l365d", "median"),
            mean_estimated_revenue=("estimated_revenue_l365d", "mean"),
            median_estimated_occupancy=("estimated_occupancy_l365d", "median"),
            median_rating=("review_scores_rating", "median"),
            median_reviews_ltm=("number_of_reviews_ltm", "median"),
        )
        .reset_index()
    )

    neighbourhood = neighbourhood[
        neighbourhood["listings"] >= 50
    ].sort_values("median_estimated_revenue", ascending=False)

    q75 = one_bed["estimated_revenue_l365d"].quantile(0.75)
    one_bed["performance_group"] = np.where(
        one_bed["estimated_revenue_l365d"] >= q75,
        "Top 25%",
        "Other 75%",
    )

    performance = (
        one_bed.groupby("performance_group")
        .agg(
            listings=("id", "count"),
            median_estimated_revenue=("estimated_revenue_l365d", "median"),
            median_price=("price_num", "median"),
            median_estimated_occupancy=("estimated_occupancy_l365d", "median"),
            median_rating=("review_scores_rating", "median"),
            median_reviews_ltm=("number_of_reviews_ltm", "median"),
            median_calendar_unavailability=(
                "calendar_unavailability_rate",
                "median",
            ),
            median_minimum_nights=("minimum_nights", "median"),
        )
    )

    performance["superhost_share"] = (
        one_bed.groupby("performance_group")["host_is_superhost"]
        .apply(lambda s: (s == "t").mean())
    )

    return room_summary, neighbourhood, performance.reset_index()


def make_charts(room, neighbourhood, performance, seasonality, calendar_monthly):
    plot_df = room.sort_values("median_estimated_revenue")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(plot_df["room_type"], plot_df["median_estimated_revenue"])
    ax.set_title("Median Estimated Annual Revenue by Room Type")
    ax.set_xlabel("Median estimated annual revenue ($)")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(IMAGES / "median_revenue_by_room_type.png", dpi=180)
    plt.close(fig)

    top_nb = neighbourhood.head(10).sort_values("median_estimated_revenue")
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(
        top_nb["neighbourhood_cleansed"],
        top_nb["median_estimated_revenue"],
    )
    ax.set_title(
        "1-Bedroom Entire Homes: Top Neighbourhoods by Median Estimated Revenue"
    )
    ax.set_xlabel("Median estimated annual revenue ($)")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(IMAGES / "one_bed_neighbourhood_benchmark.png", dpi=180)
    plt.close(fig)

    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    seasonality = seasonality.copy()
    seasonality["month_name"] = seasonality["month_num"].map(
        dict(enumerate(month_names, start=1))
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(
        seasonality["month_name"],
        seasonality["avg_monthly_share"] * 100,
        marker="o",
    )
    ax.set_title("Seasonality in Toronto Airbnb Review Activity (2024–2025)")
    ax.set_xlabel("Month")
    ax.set_ylabel("Average share of annual reviews (%)")
    fig.tight_layout()
    fig.savefig(IMAGES / "review_seasonality.png", dpi=180)
    plt.close(fig)

    full_months = calendar_monthly[
        (calendar_monthly["month"] >= "2026-10")
        & (calendar_monthly["month"] <= "2027-08")
    ]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        full_months["month"],
        full_months["unavailability_rate"] * 100,
        marker="o",
    )
    ax.set_title("Calendar Unavailability by Month")
    ax.set_xlabel("Month")
    ax.set_ylabel("Unavailable calendar days (%)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(IMAGES / "calendar_unavailability.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(
        performance["performance_group"],
        performance["superhost_share"] * 100,
    )
    ax.set_title("Superhost Share: Top-Revenue 1BR Listings vs. Others")
    ax.set_xlabel("")
    ax.set_ylabel("Superhost share (%)")
    fig.tight_layout()
    fig.savefig(IMAGES / "superhost_share.png", dpi=180)
    plt.close(fig)


def main():
    df = load_and_clean_listings()
    valid_ids = set(df["id"].astype("int64"))

    calendar_monthly, calendar_listing = aggregate_calendar(valid_ids)
    df = df.merge(
        calendar_listing,
        left_on="id",
        right_on="listing_id",
        how="left",
    )

    monthly_reviews, seasonality = analyze_reviews(valid_ids)
    room, neighbourhood, performance = build_tables(df)

    room.to_csv(OUTPUTS / "room_type_summary.csv", index=False)
    neighbourhood.to_csv(
        OUTPUTS / "one_bed_neighbourhood_benchmark.csv",
        index=False,
    )
    performance.to_csv(
        OUTPUTS / "top_quartile_comparison.csv",
        index=False,
    )
    monthly_reviews.to_csv(
        OUTPUTS / "monthly_review_counts.csv",
        index=False,
    )
    seasonality.to_csv(
        OUTPUTS / "review_seasonality_2024_2025.csv",
        index=False,
    )
    calendar_monthly.to_csv(
        OUTPUTS / "calendar_unavailability_by_month.csv",
        index=False,
    )

    make_charts(
        room,
        neighbourhood,
        performance,
        seasonality,
        calendar_monthly,
    )

    print(f"Analysis complete. {len(df):,} listings used.")


if __name__ == "__main__":
    main()

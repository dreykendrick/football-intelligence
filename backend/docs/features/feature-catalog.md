# MVP-A Feature Catalog & Metadata Specifications

| Feature Key | Version | Category | Data Type | Min History | Missing Policy | Description |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `home_matches_played_v1` | 1.0.0 | HISTORICAL_COUNTS | INT | 0 | INSUFFICIENT_HISTORY | Number of matches played by home team prior to cutoff. |
| `away_matches_played_v1` | 1.0.0 | HISTORICAL_COUNTS | INT | 0 | INSUFFICIENT_HISTORY | Number of matches played by away team prior to cutoff. |
| `total_matches_played_v1` | 1.0.0 | HISTORICAL_COUNTS | INT | 0 | INSUFFICIENT_HISTORY | Combined total historical matches played by home/away teams. |
| `home_goals_scored_avg_v1` | 1.0.0 | GOALS | FLOAT | 1 | INSUFFICIENT_HISTORY | Average goals scored per home match by home team. |
| `home_goals_conceded_avg_v1` | 1.0.0 | GOALS | FLOAT | 1 | INSUFFICIENT_HISTORY | Average goals conceded per home match by home team. |
| `away_goals_scored_avg_v1` | 1.0.0 | GOALS | FLOAT | 1 | INSUFFICIENT_HISTORY | Average goals scored per away match by away team. |
| `away_goals_conceded_avg_v1` | 1.0.0 | GOALS | FLOAT | 1 | INSUFFICIENT_HISTORY | Average goals conceded per away match by away team. |
| `home_attack_strength_v1` | 1.0.0 | STRENGTH | FLOAT | 1 | INSUFFICIENT_HISTORY | Home team average goals scored / league home average. |
| `away_attack_strength_v1` | 1.0.0 | STRENGTH | FLOAT | 1 | INSUFFICIENT_HISTORY | Away team average goals scored / league away average. |
| `home_defense_strength_v1` | 1.0.0 | STRENGTH | FLOAT | 1 | INSUFFICIENT_HISTORY | Home team average goals conceded / league away average. |
| `away_defense_strength_v1` | 1.0.0 | STRENGTH | FLOAT | 1 | INSUFFICIENT_HISTORY | Away team average goals conceded / league home average. |
| `home_recent_ppg_v1` | 1.0.0 | FORM | FLOAT | 1 | INSUFFICIENT_HISTORY | Points per match earned by home team in last 5 matches. |
| `away_recent_ppg_v1` | 1.0.0 | FORM | FLOAT | 1 | INSUFFICIENT_HISTORY | Points per match earned by away team in last 5 matches. |
| `home_recent_goals_scored_v1` | 1.0.0 | FORM | FLOAT | 1 | INSUFFICIENT_HISTORY | Total goals scored by home team in last 5 matches. |
| `away_recent_goals_conceded_v1` | 1.0.0 | FORM | FLOAT | 1 | INSUFFICIENT_HISTORY | Total goals conceded by away team in last 5 matches. |
| `home_elo_v1` | 1.0.0 | ELO | FLOAT | 0 | INSUFFICIENT_HISTORY | Sequential pre-match Elo rating for home team. |
| `away_elo_v1` | 1.0.0 | ELO | FLOAT | 0 | INSUFFICIENT_HISTORY | Sequential pre-match Elo rating for away team. |
| `elo_difference_v1` | 1.0.0 | ELO | FLOAT | 0 | INSUFFICIENT_HISTORY | Home pre-match Elo minus away pre-match Elo. |
| `home_rest_days_v1` | 1.0.0 | REST_SCHEDULE | FLOAT | 1 | INSUFFICIENT_HISTORY | Days elapsed since home team's previous match. |
| `away_rest_days_v1` | 1.0.0 | REST_SCHEDULE | FLOAT | 1 | INSUFFICIENT_HISTORY | Days elapsed since away team's previous match. |
| `rest_days_difference_v1` | 1.0.0 | REST_SCHEDULE | FLOAT | 1 | INSUFFICIENT_HISTORY | Home rest days minus away rest days. |
| `home_matches_last_14d_v1` | 1.0.0 | REST_SCHEDULE | INT | 0 | INSUFFICIENT_HISTORY | Home team matches played in last 14 days. |
| `away_matches_last_14d_v1` | 1.0.0 | REST_SCHEDULE | INT | 0 | INSUFFICIENT_HISTORY | Away team matches played in last 14 days. |

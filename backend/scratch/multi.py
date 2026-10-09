import sys, os, sqlite3, numpy as np
sys.path.append('c:/Users/kibaj/FB/backend')
from app.models.baselines.attack_defense_poisson import _fit_competition_poisson

conn = sqlite3.connect('c:/Users/kibaj/FB/backend/football_dev.db')
c = conn.cursor()
c.execute('''
    SELECT m.home_team_id, m.away_team_id, m.home_score, m.away_score
    FROM matches m JOIN seasons s ON m.season_id = s.id
    WHERE m.status = 'FINISHED' AND s.competition_id = '719f254248c84352af579f0b81a5562b'
    AND s.season_year NOT LIKE '%2023%'
''')
rows = c.fetchall()

teams = sorted(list(set([r[0] for r in rows] + [r[1] for r in rows])))
t_map = {t: i for i, t in enumerate(teams)}
h_idx = np.array([t_map[r[0]] for r in rows])
a_idx = np.array([t_map[r[1]] for r in rows])
h_goals = np.array([r[2] for r in rows], dtype=np.float64)
a_goals = np.array([r[3] for r in rows], dtype=np.float64)
num_teams = len(teams)

print('--- DC MULTI-START ---')
for r_start in [0.0, 0.05, -0.05]:
    res = _fit_competition_poisson(initial_rho=r_start, home_indices=h_idx, away_indices=a_idx, home_goals=h_goals, away_goals=a_goals, num_teams=num_teams, optimize_rho=True)
    print(f"Start {r_start}: success={res['success']} final_rho={res['rho']:.4f} obj={res['final_objective']:.4f} iter={res['iterations']}")

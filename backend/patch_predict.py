import re

with open("app/models/baselines/attack_defense_poisson.py", "r") as f:
    content = f.read()

pattern = re.compile(r'(        # Derive probability distribution through GoalDistributionEngine\n        )(matrix = self\._distribution_engine\.compute_score_matrix\(lambda_home, lambda_away\))')

new_content = r'''\1rho_val = float(comp_model.get("dixon_coles_rho", 0.0)) if use_learned_teams else 0.0
        matrix = self._distribution_engine.compute_score_matrix(lambda_home, lambda_away, rho=rho_val)'''

patched = pattern.sub(new_content, content)

with open("app/models/baselines/attack_defense_poisson.py", "w") as f:
    f.write(patched)

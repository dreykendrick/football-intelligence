import re

with open("app/models/baselines/attack_defense_poisson.py", "r") as f:
    content = f.read()

new_init = '''    def __init__(
        self,
        regularization_gamma: float = 0.2,
        min_matches_history: int = 5,
        max_iter: int = 500,
        tol: float = 1e-6,
        time_decay_half_life_days: float | None = None,
        optimize_rho: bool = False,
    ) -> None:
        self.regularization_gamma = regularization_gamma
        self.min_matches_history = min_matches_history
        self.max_iter = max_iter
        self.tol = tol
        self.time_decay_half_life_days = time_decay_half_life_days
        self.optimize_rho = optimize_rho
        
        self.artifact: TrainedModelArtifact | None = None
        self._distribution_engine = GoalDistributionEngine()
        
        if self.optimize_rho:
            self.model_key = "dixon_coles_poisson_v1"
        elif self.time_decay_half_life_days is not None:
            self.model_key = "attack_defense_poisson_decay_v1"
        else:
            self.model_key = "attack_defense_poisson_v1"'''

pattern = re.compile(r'    def __init__\([\s\S]*?self\._distribution_engine = GoalDistributionEngine\(\)', re.MULTILINE)
new_content = pattern.sub(new_init, content)

with open("app/models/baselines/attack_defense_poisson.py", "w") as f:
    f.write(new_content)

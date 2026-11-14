# Hagar benchmark P1 — modello 8B

Modello: `llama3.1-8b`

- chat: 1/1
- JSON valido: 1/1
- JSON field F1: 0.0
- tool: 1/1
- tool args: 1.0
- qualità: 0.8682
- memoria: 0.7083
- coding eseguibile: 1.0000
- production p50/p95: 7994.02 / 7994.02 ms
- tool nel prompt production: 42

```json
{
  "model": "llama3.1-8b",
  "text": {
    "tested_at": "2026-11-14T08:48:49+00:00",
    "provider": "lmstudio",
    "model": "llama3.1-8b",
    "hardware": {
      "platform": "Windows",
      "release": "10",
      "machine": "AMD64",
      "python": "3.15.0",
      "hostname": "DESKTOP-8UB1QQ7",
      "cpu": {
        "model": "AMD Ryzen 7 5700X 8-Core Processor",
        "physical_cores": null,
        "logical_cores": 16,
        "mhz_current": null,
        "mhz_max": 3400,
        "ghz_current": null,
        "ghz_max": 3.4
      },
      "memory": {
        "total_bytes": 51444142080,
        "available_bytes": 34009915392,
        "total_gib": 47.91,
        "available_gib": 31.67
      },
      "gpus": [
        {
          "name": "NVIDIA GeForce RTX 4060",
          "vendor": "NVIDIA",
          "vram_bytes": 8585740288,
          "driver": "610.47",
          "api": "CUDA"
        }
      ]
    },
    "capabilities": {
      "chat": true,
      "structured_json": true,
      "tool_calling": true,
      "native_tools": true
    },
    "benchmarks": {
      "chat": {
        "attempts": 1,
        "successes": 1,
        "errors": [],
        "duration_ms": {
          "count": 1,
          "min": 2926.95,
          "mean": 2926.95,
          "p50": 2926.95,
          "p95": 2926.95,
          "max": 2926.95
        },
        "output_tokens_per_second": 0.683
      },
      "structured": {
        "attempts": 1,
        "valid_json": 1,
        "valid_choice": 0,
        "schema_valid": 0,
        "field_f1": 0.0,
        "errors": [],
        "duration_ms": {
          "count": 1,
          "min": 4945.68,
          "mean": 4945.68,
          "p50": 4945.68,
          "p95": 4945.68,
          "max": 4945.68
        }
      },
      "tool_call": {
        "attempts": 1,
        "successes": 1,
        "selection_accuracy": 1.0,
        "argument_matches": 1,
        "argument_accuracy": 1.0,
        "errors": [],
        "duration_ms": {
          "count": 1,
          "min": 5849.63,
          "mean": 5849.63,
          "p50": 5849.63,
          "p95": 5849.63,
          "max": 5849.63
        }
      }
    }
  },
  "quality": {
    "suite_version": 3,
    "corpus": "hagar-bench-2026-11",
    "tested_at": "2026-11-14T08:50:03+00:00",
    "attempts": 1,
    "tasks": {
      "summary": {
        "attempts": 1,
        "cases": 2,
        "scores": [
          0.8400000000000001,
          0.4
        ],
        "mean": 0.62,
        "errors": []
      },
      "translation": {
        "attempts": 1,
        "cases": 2,
        "scores": [
          0.9510773122519955,
          0.22757658287307125
        ],
        "mean": 0.5893,
        "errors": []
      },
      "extraction": {
        "attempts": 1,
        "cases": 1,
        "scores": [
          1.0
        ],
        "mean": 1.0,
        "errors": []
      },
      "instruction": {
        "attempts": 1,
        "cases": 1,
        "scores": [
          1.0
        ],
        "mean": 1.0,
        "errors": []
      },
      "reasoning": {
        "attempts": 1,
        "cases": 1,
        "scores": [
          1.0
        ],
        "mean": 1.0,
        "errors": []
      },
      "coding": {
        "attempts": 1,
        "cases": 1,
        "scores": [
          1.0
        ],
        "mean": 1.0,
        "errors": []
      },
      "memory": {
        "attempts": 1,
        "cases": 6,
        "scores": [
          1.0,
          0.75,
          1.0,
          1.0,
          0.5,
          0.0
        ],
        "mean": 0.7083,
        "errors": [],
        "case_results": [
          {
            "name": "memory_recall_simple",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 10473.87,
              "p95": 10473.87,
              "max": 10473.87
            },
            "expected": [
              "atreides"
            ],
            "forbidden": []
          },
          {
            "name": "memory_distractor",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              0.75
            ],
            "mean": 0.75,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 9574.8,
              "p95": 9574.8,
              "max": 9574.8
            },
            "expected": [
              "8443"
            ],
            "forbidden": [
              "8080"
            ]
          },
          {
            "name": "memory_contradiction",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 3632.26,
              "p95": 3632.26,
              "max": 3632.26
            },
            "expected": [
              "luca"
            ],
            "forbidden": [
              "mario"
            ]
          },
          {
            "name": "memory_instruction_retention",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 3833.94,
              "p95": 3833.94,
              "max": 3833.94
            },
            "expected": [
              "parigi"
            ],
            "forbidden": []
          },
          {
            "name": "memory_long_context",
            "task": "memory",
            "long_context": true,
            "attempts": 1,
            "scores": [
              0.5
            ],
            "mean": 0.5,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 5627.3,
              "p95": 5627.3,
              "max": 5627.3
            },
            "expected": [
              "zenith-42",
              "zenith 42"
            ],
            "forbidden": []
          },
          {
            "name": "memory_false_premise",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              0.0
            ],
            "mean": 0.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 6800.06,
              "p95": 6800.06,
              "max": 6800.06
            },
            "expected": [
              "vega"
            ],
            "forbidden": [
              "sirio"
            ]
          }
        ]
      },
      "coding_exec": {
        "attempts": 1,
        "cases": 2,
        "scores": [
          1.0,
          1.0
        ],
        "mean": 1.0,
        "errors": [],
        "case_results": [
          {
            "name": "coding_add",
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 4164.42,
              "p95": 4164.42,
              "max": 4164.42
            }
          },
          {
            "name": "coding_is_even",
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 5373.83,
              "p95": 5373.83,
              "max": 5373.83
            }
          }
        ]
      }
    },
    "cases": [
      {
        "name": "summary_technical",
        "attempts": 1,
        "scores": [
          0.8400000000000001
        ],
        "mean": 0.84,
        "errors": []
      },
      {
        "name": "summary_broker",
        "attempts": 1,
        "scores": [
          0.4
        ],
        "mean": 0.4,
        "errors": []
      },
      {
        "name": "translation_it_en",
        "attempts": 1,
        "scores": [
          0.9510773122519955
        ],
        "mean": 0.9511,
        "errors": []
      },
      {
        "name": "translation_en_it",
        "attempts": 1,
        "scores": [
          0.22757658287307125
        ],
        "mean": 0.2276,
        "errors": []
      },
      {
        "name": "extraction",
        "attempts": 1,
        "scores": [
          1.0
        ],
        "mean": 1.0,
        "errors": []
      },
      {
        "name": "instruction",
        "attempts": 1,
        "scores": [
          1.0
        ],
        "mean": 1.0,
        "errors": []
      },
      {
        "name": "reasoning",
        "attempts": 1,
        "scores": [
          1.0
        ],
        "mean": 1.0,
        "errors": []
      },
      {
        "name": "coding",
        "attempts": 1,
        "scores": [
          1.0
        ],
        "mean": 1.0,
        "errors": []
      }
    ],
    "overall": 0.8682
  },
  "memory": {
    "suite_version": 1,
    "tested_at": "2026-11-14T08:50:43+00:00",
    "attempts": 1,
    "tasks": {
      "memory": {
        "attempts": 1,
        "cases": 6,
        "scores": [
          1.0,
          0.75,
          1.0,
          1.0,
          0.5,
          0.0
        ],
        "mean": 0.7083,
        "errors": [],
        "case_results": [
          {
            "name": "memory_recall_simple",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 10473.87,
              "p95": 10473.87,
              "max": 10473.87
            },
            "expected": [
              "atreides"
            ],
            "forbidden": []
          },
          {
            "name": "memory_distractor",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              0.75
            ],
            "mean": 0.75,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 9574.8,
              "p95": 9574.8,
              "max": 9574.8
            },
            "expected": [
              "8443"
            ],
            "forbidden": [
              "8080"
            ]
          },
          {
            "name": "memory_contradiction",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 3632.26,
              "p95": 3632.26,
              "max": 3632.26
            },
            "expected": [
              "luca"
            ],
            "forbidden": [
              "mario"
            ]
          },
          {
            "name": "memory_instruction_retention",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 3833.94,
              "p95": 3833.94,
              "max": 3833.94
            },
            "expected": [
              "parigi"
            ],
            "forbidden": []
          },
          {
            "name": "memory_long_context",
            "task": "memory",
            "long_context": true,
            "attempts": 1,
            "scores": [
              0.5
            ],
            "mean": 0.5,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 5627.3,
              "p95": 5627.3,
              "max": 5627.3
            },
            "expected": [
              "zenith-42",
              "zenith 42"
            ],
            "forbidden": []
          },
          {
            "name": "memory_false_premise",
            "task": "memory",
            "long_context": false,
            "attempts": 1,
            "scores": [
              0.0
            ],
            "mean": 0.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 6800.06,
              "p95": 6800.06,
              "max": 6800.06
            },
            "expected": [
              "vega"
            ],
            "forbidden": [
              "sirio"
            ]
          }
        ]
      }
    },
    "overall": 0.7083
  },
  "coding": {
    "suite_version": 1,
    "tested_at": "2026-11-14T08:50:53+00:00",
    "attempts": 1,
    "tasks": {
      "coding_exec": {
        "attempts": 1,
        "cases": 2,
        "scores": [
          1.0,
          1.0
        ],
        "mean": 1.0,
        "errors": [],
        "case_results": [
          {
            "name": "coding_add",
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 4164.42,
              "p95": 4164.42,
              "max": 4164.42
            }
          },
          {
            "name": "coding_is_even",
            "attempts": 1,
            "scores": [
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 5373.83,
              "p95": 5373.83,
              "max": 5373.83
            }
          }
        ]
      }
    },
    "overall": 1.0
  },
  "production": {
    "tested_at": "2026-11-14T08:51:01+00:00",
    "attempts": 1,
    "prompt_chars": 2140,
    "system_chars": 2047,
    "tools": 42,
    "p50_ms": 7994.02,
    "p95_ms": 7994.02,
    "samples": [
      {
        "duration_ms": 7994.02,
        "answer_chars": 157,
        "error": null
      }
    ]
  }
}
```

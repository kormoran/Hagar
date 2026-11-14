# Hagar benchmark P1 — modello 8B

Modello: `lmstudio-community/meta-llama-3.1-8b-instruct`

- chat: 1/1
- JSON valido: 1/1
- JSON field F1: 0.2857
- tool: 1/1
- tool args: 1.0
- qualità: 0.1113
- memoria: 0.5833
- coding eseguibile: 0.0000
- production p50/p95: 2938.25 / 2938.25 ms
- tool nel prompt production: 42

```json
{
  "model": "lmstudio-community/meta-llama-3.1-8b-instruct",
  "text": {
    "tested_at": "2026-11-14T08:46:25+00:00",
    "provider": "lmstudio",
    "model": "lmstudio-community/meta-llama-3.1-8b-instruct",
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
        "available_bytes": 34449342464,
        "total_gib": 47.91,
        "available_gib": 32.08
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
          "min": 3007.3,
          "mean": 3007.3,
          "p50": 3007.3,
          "p95": 3007.3,
          "max": 3007.3
        },
        "output_tokens_per_second": 12.968
      },
      "structured": {
        "attempts": 1,
        "valid_json": 1,
        "valid_choice": 0,
        "schema_valid": 0,
        "field_f1": 0.2857,
        "errors": [],
        "duration_ms": {
          "count": 1,
          "min": 3060.13,
          "mean": 3060.13,
          "p50": 3060.13,
          "p95": 3060.13,
          "max": 3060.13
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
          "min": 2531.21,
          "mean": 2531.21,
          "p50": 2531.21,
          "p95": 2531.21,
          "max": 2531.21
        }
      }
    }
  },
  "quality": {
    "suite_version": 3,
    "corpus": "hagar-bench-2026-11",
    "tested_at": "2026-11-14T08:46:48+00:00",
    "attempts": 1,
    "tasks": {
      "summary": {
        "attempts": 1,
        "cases": 2,
        "scores": [
          0.2,
          0.6000000000000001
        ],
        "mean": 0.4,
        "errors": []
      },
      "translation": {
        "attempts": 1,
        "cases": 2,
        "scores": [
          0.3509011897403894,
          0.18452948180173473
        ],
        "mean": 0.2677,
        "errors": []
      },
      "extraction": {
        "attempts": 1,
        "cases": 1,
        "scores": [
          0.0
        ],
        "mean": 0.0,
        "errors": []
      },
      "instruction": {
        "attempts": 1,
        "cases": 1,
        "scores": [
          0.0
        ],
        "mean": 0.0,
        "errors": []
      },
      "reasoning": {
        "attempts": 1,
        "cases": 1,
        "scores": [
          0.0
        ],
        "mean": 0.0,
        "errors": []
      },
      "coding": {
        "attempts": 1,
        "cases": 1,
        "scores": [
          0.0
        ],
        "mean": 0.0,
        "errors": []
      },
      "memory": {
        "attempts": 1,
        "cases": 6,
        "scores": [
          1.0,
          1.0,
          0.0,
          0.0,
          0.5,
          1.0
        ],
        "mean": 0.5833,
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
              "p50": 4324.03,
              "p95": 4324.03,
              "max": 4324.03
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
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 2565.43,
              "p95": 2565.43,
              "max": 2565.43
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
              0.0
            ],
            "mean": 0.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 2488.93,
              "p95": 2488.93,
              "max": 2488.93
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
              0.0
            ],
            "mean": 0.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 2529.01,
              "p95": 2529.01,
              "max": 2529.01
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
              "p50": 2788.01,
              "p95": 2788.01,
              "max": 2788.01
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
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 2651.09,
              "p95": 2651.09,
              "max": 2651.09
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
          0.0,
          0.0
        ],
        "mean": 0.0,
        "errors": [
          "Traceback (most recent call last):\n  File \"<string>\", line 3, in <module>\n    assert add(2, 3) == 5\n           ^^^\nNameError: name 'add' is not defined",
          "Traceback (most recent call last):\n  File \"<string>\", line 3, in <module>\n    assert is_even(2) is True\n           ^^^^^^^\nNameError: name 'is_even' is not defined"
        ],
        "case_results": [
          {
            "name": "coding_add",
            "attempts": 1,
            "scores": [
              0.0
            ],
            "mean": 0.0,
            "errors": [
              "Traceback (most recent call last):\n  File \"<string>\", line 3, in <module>\n    assert add(2, 3) == 5\n           ^^^\nNameError: name 'add' is not defined"
            ],
            "duration_ms": {
              "count": 1,
              "p50": 2782.32,
              "p95": 2782.32,
              "max": 2782.32
            }
          },
          {
            "name": "coding_is_even",
            "attempts": 1,
            "scores": [
              0.0
            ],
            "mean": 0.0,
            "errors": [
              "Traceback (most recent call last):\n  File \"<string>\", line 3, in <module>\n    assert is_even(2) is True\n           ^^^^^^^\nNameError: name 'is_even' is not defined"
            ],
            "duration_ms": {
              "count": 1,
              "p50": 2611.24,
              "p95": 2611.24,
              "max": 2611.24
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
          0.2
        ],
        "mean": 0.2,
        "errors": []
      },
      {
        "name": "summary_broker",
        "attempts": 1,
        "scores": [
          0.6000000000000001
        ],
        "mean": 0.6,
        "errors": []
      },
      {
        "name": "translation_it_en",
        "attempts": 1,
        "scores": [
          0.3509011897403894
        ],
        "mean": 0.3509,
        "errors": []
      },
      {
        "name": "translation_en_it",
        "attempts": 1,
        "scores": [
          0.18452948180173473
        ],
        "mean": 0.1845,
        "errors": []
      },
      {
        "name": "extraction",
        "attempts": 1,
        "scores": [
          0.0
        ],
        "mean": 0.0,
        "errors": []
      },
      {
        "name": "instruction",
        "attempts": 1,
        "scores": [
          0.0
        ],
        "mean": 0.0,
        "errors": []
      },
      {
        "name": "reasoning",
        "attempts": 1,
        "scores": [
          0.0
        ],
        "mean": 0.0,
        "errors": []
      },
      {
        "name": "coding",
        "attempts": 1,
        "scores": [
          0.0
        ],
        "mean": 0.0,
        "errors": []
      }
    ],
    "overall": 0.1113
  },
  "memory": {
    "suite_version": 1,
    "tested_at": "2026-11-14T08:47:06+00:00",
    "attempts": 1,
    "tasks": {
      "memory": {
        "attempts": 1,
        "cases": 6,
        "scores": [
          1.0,
          1.0,
          0.0,
          0.0,
          0.5,
          1.0
        ],
        "mean": 0.5833,
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
              "p50": 4324.03,
              "p95": 4324.03,
              "max": 4324.03
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
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 2565.43,
              "p95": 2565.43,
              "max": 2565.43
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
              0.0
            ],
            "mean": 0.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 2488.93,
              "p95": 2488.93,
              "max": 2488.93
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
              0.0
            ],
            "mean": 0.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 2529.01,
              "p95": 2529.01,
              "max": 2529.01
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
              "p50": 2788.01,
              "p95": 2788.01,
              "max": 2788.01
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
              1.0
            ],
            "mean": 1.0,
            "errors": [],
            "duration_ms": {
              "count": 1,
              "p50": 2651.09,
              "p95": 2651.09,
              "max": 2651.09
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
    "overall": 0.5833
  },
  "coding": {
    "suite_version": 1,
    "tested_at": "2026-11-14T08:47:11+00:00",
    "attempts": 1,
    "tasks": {
      "coding_exec": {
        "attempts": 1,
        "cases": 2,
        "scores": [
          0.0,
          0.0
        ],
        "mean": 0.0,
        "errors": [
          "Traceback (most recent call last):\n  File \"<string>\", line 3, in <module>\n    assert add(2, 3) == 5\n           ^^^\nNameError: name 'add' is not defined",
          "Traceback (most recent call last):\n  File \"<string>\", line 3, in <module>\n    assert is_even(2) is True\n           ^^^^^^^\nNameError: name 'is_even' is not defined"
        ],
        "case_results": [
          {
            "name": "coding_add",
            "attempts": 1,
            "scores": [
              0.0
            ],
            "mean": 0.0,
            "errors": [
              "Traceback (most recent call last):\n  File \"<string>\", line 3, in <module>\n    assert add(2, 3) == 5\n           ^^^\nNameError: name 'add' is not defined"
            ],
            "duration_ms": {
              "count": 1,
              "p50": 2782.32,
              "p95": 2782.32,
              "max": 2782.32
            }
          },
          {
            "name": "coding_is_even",
            "attempts": 1,
            "scores": [
              0.0
            ],
            "mean": 0.0,
            "errors": [
              "Traceback (most recent call last):\n  File \"<string>\", line 3, in <module>\n    assert is_even(2) is True\n           ^^^^^^^\nNameError: name 'is_even' is not defined"
            ],
            "duration_ms": {
              "count": 1,
              "p50": 2611.24,
              "p95": 2611.24,
              "max": 2611.24
            }
          }
        ]
      }
    },
    "overall": 0.0
  },
  "production": {
    "tested_at": "2026-11-14T08:47:14+00:00",
    "attempts": 1,
    "prompt_chars": 2140,
    "system_chars": 2047,
    "tools": 42,
    "p50_ms": 2938.25,
    "p95_ms": 2938.25,
    "samples": [
      {
        "duration_ms": 2938.25,
        "answer_chars": 85,
        "error": null
      }
    ]
  }
}
```

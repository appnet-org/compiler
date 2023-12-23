# ADN Compiler Examples

* `graph`: graph specification examples.
* `element`: element speficiation examples.
* `property`: hand-written element properties.

## Element Examples:
| Element                   | Description                                             | Stateful?   | 
|---------------------------|---------------------------------------------------------|-------------|
| Fault Injection           | Probabilistically drop request                          | ✓           |
| Cache                     | Generic Cache for RPC                                   | ✓           | 
| Rate Limiting             | Control the rate of backend requests                    | ✓           | 
| Load Balancing            | Load balance across all service replicas                | ✓           | 
| Logging                   | Record the request content to disk                      | ✓           |
| Mutation                  | Modify the RPC content                                  |             | 
| Application Firewall      | Rejects an RPC based on pattern matching                | ✓           |
| Metrics                   | Monitor the RPC latency and success rate                | ✓           | 
| Admission Control         | Drop requests based on success rates                    | ✓           | 
| Compression               | Compress certain RPC fields                             |             | 
| Encryption                | Encrypt certain RPC fields                              |             | 
| Bandwidth Limit           | Control the size of data flow to the backends           | ✓           | 
| Circuit Breaking          | Limit the impact of undesirable network peculiarities   | ✓           |

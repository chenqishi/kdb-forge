# invoke_cli

Inputs: intercepted controller command string or argv list. Outputs: isolate actual script argv after python command; feed actual insert_data_to_search_index to Fire with original options. Capture return/statistics and Fire output. Keep zero exit for ordinary False-row statistics to expose controller contract defect; exceptions become nonzero boundary. SQL/side effects: invokes real business and engine with captured ES boundary only.

# Code for dataset extraction of the Evolution Dark Web Market from Dark Net Market archive source files

This code was used in the production of the dataset published under the title [A large-scale longitudinal structured dataset of the dark web cryptomarket Evolution (2014–2015)](https://zenodo.org/records/10156522) with detailed descriptions and completeness analysis in this [Data Descriptor](https://doi.org/10.48550/arXiv.2311.11878).

The code was run using Python 3.8.10, with package versions: numpy 1.23.0 and pandas 1.4.3.

Steps to recreate dataset creation:
  1. Obtain and decompress raw source file of the Dark Web Marketplace Evolution from [Gwern Branwen, Nicolas Christin, David Décary-Hétu, Rasmus Munksgaard Andersen, StExo, El Presidente, Anonymous, Daryl Lau, Sohhlz, Delyan Kratunov, Vince Cakic, Van Buskirk, Whom, Michael McKenna, Sigi Goode. “Dark Net Market archives, 2011–2015”, 2015-07-12. Web. [Accessed 2021-07-24]](https://gwern.net/dnm-archive)
  2. Run first python file with usage: "1-extract-data.py [-h] -in INDIR -out OUTDIR".
     Here INDIR should be the path to the base folder of the decompressed raw source files.
  3. Run second python file with usage: "2-preprocess-forum.py [-h] -in INDIR -out OUTDIR".
     Here INDIR should match the OUTDIR of the previous step and OUTDIR should specify the folder to which the final data files are to be stored.
  4. Run third python file with usage: "3-preprocess-market.py [-h] -in INDIR -out OUTDIR".
     Here INDIR should match the OUTDIR of step 2 and OUTDIR should match the OUTDIR of step 3.
  5. Run Fourth python file with usage: "4-generate-network.py [-h] -dir INOUTDIR [-np NUMPOSTS] [-mt MAXTIMEDIFF] [-mw MINWEIGHT] [-tt TIMETILL] [-fp FIRSTPOST] [-fw FIRSTWEIGHT] [-wp WEIGHTPRECISION]".
     Here INOUTDIR should match the OUTDIR used for steps 3 and 4. The default values for all other parameters reconstructs the published dataset.
  6. The full dataset should now have been reconstructed.




# Project Plan

Generate a deezer playlist based on a give input file. The input file will be a CSV file with one of the following formats:

* title,artist,album,isrc, (importing tracks; only title field is required, the rest are optional)
* title,artist,upc, (importing albums; only the "title" and "artist" fields are required)
* artist, (importing artists; only the "artist" field is required)

When only a list of artists is provided, the playlist will be generated based on the top tracks of those artists. When a list of albums is provided, the playlist will be generated based on the tracks of those albums. When a list of tracks is provided, the playlist will be generated based on those tracks. Each may optionally include related tracks or artists, if the user chooses to include them via command line options.

Data retrieved will be cached locally to avoid hitting the API rate limits. A lightweight database type has to be chosen during development, but the final product should be able to support PostgreSQL, too. The database will store the retrieved data as well as the generated playlists.

Finally the generated playlist will be submitted to the user's Deezer account. The user will be able to choose whether to create a new playlist or to add the tracks to an existing playlist. The user will also be able to choose the name and description of the playlist, as well as its privacy settings (public or private).

The project will be developed in Python. The code will be organized in a modular way, with separate modules for data retrieval, data caching, playlist generation, and playlist submission. The code will be well-documented and tested. The project will be open source and hosted on GitHub. The project will be licensed under the MIT License. The project will be developed using Poetry for dependency management and packaging. The project will be developed using Git for version control.

## Documentation

* https://support.deezer.com/hc/en-gb/articles/360011538897-Deezer-FAQs-For-Developers
* https://developers.deezer.com/api

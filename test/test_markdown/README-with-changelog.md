This is a test Markdown file for gdasset.

<!-- gdasset: markdown
This is an embedded markdown paragraph.

* Here's a list

And some <mailto:embedded@autolinks.com> https://autolinks.com/embedded
as well as some [regular links][https://example.com/regular]
 -->

Here's another paragraph:
 * And a list
 * With several items
 * This one even has an embedded paragraph
   <!-- gdasset: markdown
   This is embedded markdown in an embedded paragraph, just to test it ends up in the right place in the tree
   -->
   
   Like this
    * And a sublist!
    <!-- gdasset: exclude -->
    * This shouldn't be visible
 * But this one should show up, since excludes are parsed within their containing elements
   * And this is another sublist

<!-- gdasset: changelog
     items: 3
     heading: Changes -->

![Screenshot 1](screenshots/screenshot1.png "Alt for screenshot 1")
![Screenshot 2](screenshots/screenshot2.jpg "Alt for screenshot 2")

Send praise and hate to nowhere@example.com, or <mailto:stillnothere@example.com>.

And here are my videos:

[First, the youtube one](http://youtu.be/12345678)
[And then, the plain link one](http://some.where.example.com/myassets/video.mp4)

<!-- gdasset: exclude -->

Here's some extended stuff that I don't want to include in the asset's
library description, perhaps it's a table of contents

<!-- gdasset: include -->

But this part is very important and should be kept.

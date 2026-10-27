# A Check needs two Source classes and stops on disagreement

A Check compares a Claim across at least two Sources from **different Source classes**. A Source class groups Sources that share one upstream, so a vendor and its reseller cannot confirm each other, and a manual search of the same vendor cannot confirm it either.

The Check compares the Claim, not the raw number: both Sources must answer true or both false. Where the Tenant requires equality, the Check declares it and the values must be equal after the declared unit conversion.

If the Sources do not confirm, the Run **stops**. Both values and both Anchors go to a Person. There is no tolerance and no Source precedence: a tolerance guesses, and precedence hides a disagreement.

**Consequence:** stopping is a success case, not an error. It is the product.

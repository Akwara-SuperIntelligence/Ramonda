# A Check compares Claims across Source classes, and stops on disagreement

A Claim is a statement a Case needs to be true, such as "the total is more than 10,000". A Check requires at least two Sources from **different Source classes**. A Source class groups Sources that share an upstream failure mode, so a screening vendor and its reseller are one class, and an analyst's manual search of the same vendor cannot corroborate it. Two Sources in one class never satisfy a Check.

A Check compares the Claim, not a raw number: both Sources must answer true or both must answer false. This removes false differences from rounding and FX without introducing a tolerance. Where the client requires exact equality, the Check declares `compare: exact` and the values must be equal after the declared unit conversion.

If the Sources do not confirm the Claim, the Case **stops**. Both values and both Anchors are returned side by side, and a person resolves it. There is no tolerance band and no source precedence: a tolerance guesses, and precedence hides a disagreement. Every Check outcome is Evidence, including the confirmations, so the regulator bundle can show what was verified as well as what failed.

An email may announce a stop. It may never approve one: an email cannot prove who clicked or what they saw.

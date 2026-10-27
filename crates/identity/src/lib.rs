//! Who may see what. The tenant always comes from the token, never the request body.

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Classification {
    Public,
    Internal,
    Confidential,
    Restricted,
}

#[derive(Debug, Clone)]
pub struct Caller {
    pub tenant: String,
    pub principal: String,
    pub groups: Vec<String>,
    pub clearance: Classification,
}

impl Caller {
    pub fn may_see(&self, doc: Classification) -> bool {
        doc <= self.clearance
    }
}
